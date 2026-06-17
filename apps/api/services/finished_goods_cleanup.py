from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models import FinalProductStock


AUTO_GENERATED_VARIANT_PATTERNS = (
    "plain white",
    "white cup",
    "default cup",
    "generic cup",
    "fallback cup",
    "placeholder",
    "standard/white",
    "standard box",
)


@dataclass(frozen=True)
class FinishedGoodsCleanupRow:
    id: int
    variant_name: str
    created_by: str
    source: str
    last_updated_at: str | None
    safe_to_remove: bool


def _normalized(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _identity(row: FinalProductStock) -> tuple[int, str, str]:
    return (
        int(row.product_size_ml),
        _normalized(row.variety),
        _normalized(row.packaging_size_name),
    )


def _fallback_filter():
    clauses = []
    for pattern in AUTO_GENERATED_VARIANT_PATTERNS:
        like = f"%{pattern}%"
        clauses.append(func.lower(FinalProductStock.variety).like(like))
        clauses.append(func.lower(FinalProductStock.packaging_size_name).like(like))
    return or_(*clauses)


def dry_run_auto_generated_finished_goods(
    db: Session,
    *,
    factory_id: int | str,
    explicit_identities: Iterable[tuple[int, str, str]] = (),
) -> list[FinishedGoodsCleanupRow]:
    keep = {
        (int(size), _normalized(variety), _normalized(packaging))
        for size, variety, packaging in explicit_identities
    }
    rows = (
        db.query(FinalProductStock)
        .filter(FinalProductStock.factory_id == str(factory_id))
        .filter(_fallback_filter())
        .order_by(FinalProductStock.product_size_ml.asc(), FinalProductStock.variety.asc())
        .all()
    )
    report: list[FinishedGoodsCleanupRow] = []
    for row in rows:
        identity = _identity(row)
        safe_to_remove = identity not in keep
        report.append(
            FinishedGoodsCleanupRow(
                id=int(row.id),
                variant_name=" ".join(
                    part
                    for part in (f"{row.product_size_ml}ml", row.variety, row.packaging_size_name)
                    if part
                ),
                created_by="unknown",
                source="legacy_finished_goods_auto_sync_or_default_payload",
                last_updated_at=row.updated_at.isoformat() if row.updated_at else None,
                safe_to_remove=safe_to_remove,
            )
        )
    return report


def remove_auto_generated_finished_goods(
    db: Session,
    *,
    factory_id: int | str,
    explicit_identities: Iterable[tuple[int, str, str]] = (),
) -> list[FinishedGoodsCleanupRow]:
    report = dry_run_auto_generated_finished_goods(
        db,
        factory_id=factory_id,
        explicit_identities=explicit_identities,
    )
    removable_ids = [row.id for row in report if row.safe_to_remove]
    if removable_ids:
        (
            db.query(FinalProductStock)
            .filter(FinalProductStock.factory_id == str(factory_id))
            .filter(FinalProductStock.id.in_(removable_ids))
            .delete(synchronize_session=False)
        )
        db.flush()
    return report
