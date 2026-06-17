from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    table_name: str
    factory_id: str
    variant_name: str
    created_by: str
    source: str
    created_at: str | None
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
        source = getattr(row, "source", None) or "unknown"
        is_auto_created = bool(getattr(row, "is_auto_created", False))
        is_manual_or_onboarding = source in {"manual", "onboarding"}
        safe_to_remove = identity not in keep and (is_auto_created or not is_manual_or_onboarding)
        report.append(
            FinishedGoodsCleanupRow(
                id=int(row.id),
                table_name="final_product_stock",
                factory_id=str(row.factory_id),
                variant_name=" ".join(
                    part
                    for part in (f"{row.product_size_ml}ml", row.variety, row.packaging_size_name)
                    if part
                ),
                created_by="unknown",
                source=source,
                created_at=row.created_at.isoformat() if getattr(row, "created_at", None) else None,
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
        now = datetime.now(timezone.utc)
        for row in (
            db.query(FinalProductStock)
            .filter(FinalProductStock.factory_id == str(factory_id))
            .filter(FinalProductStock.id.in_(removable_ids))
            .all()
        ):
            row.is_active = False
            row.archived_at = now
            row.is_auto_created = True
            if not row.source or row.source == "unknown":
                row.source = "legacy_auto_generated"
            db.add(row)
        db.flush()
    return report
