from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Iterable

from db import SessionLocal
from models import FinalProductStock, PackagingMetrics


def _normalized(value: str) -> str:
    return value.strip().casefold()


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _group_duplicates(
    rows: Iterable[Any],
    key_builder: Callable[[Any], tuple[Any, ...]],
) -> list[list[Any]]:
    grouped: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for row in rows:
        grouped[key_builder(row)].append(row)
    return [sorted(group, key=lambda row: row.id) for group in grouped.values() if len(group) > 1]


def _value_conflicts(rows: list[Any], fields: tuple[str, ...]) -> dict[str, list[Any]]:
    conflicts: dict[str, list[Any]] = {}
    for field in fields:
        values = {_serialize(getattr(row, field)) for row in rows}
        if len(values) > 1:
            conflicts[field] = sorted(values, key=str)
    return conflicts


def _latest_final_product(rows: list[FinalProductStock]) -> FinalProductStock:
    return max(
        rows,
        key=lambda row: (
            row.updated_at.timestamp() if row.updated_at is not None else float("-inf"),
            row.id,
        ),
    )


def _final_product_report(rows: list[FinalProductStock]) -> dict[str, Any]:
    survivor = rows[0]
    source = _latest_final_product(rows)
    return {
        "key": {
            "factory_id": survivor.factory_id,
            "product_size_ml": survivor.product_size_ml,
            "variety": _normalized(survivor.variety),
            "packaging_size_name": _normalized(survivor.packaging_size_name),
        },
        "row_ids": [row.id for row in rows],
        "suggested_merge": {
            "survivor_id": survivor.id,
            "delete_ids": [row.id for row in rows[1:]],
            "strategy": "sum stock quantities; use newest row for packaging configuration",
            "result": {
                "current_quantity": sum(row.current_quantity for row in rows),
                "total_boxes": sum(row.total_boxes for row in rows),
                "loose_packets": sum(row.loose_packets for row in rows),
                "pieces_per_packet": source.pieces_per_packet,
                "packets_per_box_limit": source.packets_per_box_limit,
            },
            "conflicts": _value_conflicts(
                rows,
                ("pieces_per_packet", "packets_per_box_limit"),
            ),
        },
    }


def _packaging_metrics_report(rows: list[PackagingMetrics]) -> dict[str, Any]:
    survivor = rows[0]
    source = rows[-1]
    return {
        "key": {
            "factory_id": survivor.factory_id,
            "cup_size_ml": survivor.cup_size_ml,
            "variant_name": _normalized(survivor.variant_name),
        },
        "row_ids": [row.id for row in rows],
        "suggested_merge": {
            "survivor_id": survivor.id,
            "delete_ids": [row.id for row in rows[1:]],
            "strategy": "keep newest row values on the lowest-id survivor",
            "value_source_id": source.id,
            "result": {
                "kg_per_box": _serialize(source.kg_per_box),
                "cups_per_box": source.cups_per_box,
            },
            "conflicts": _value_conflicts(rows, ("kg_per_box", "cups_per_box")),
        },
    }


def build_dedupe_report(session) -> dict[str, Any]:
    final_groups = _group_duplicates(
        session.query(FinalProductStock).order_by(FinalProductStock.id).all(),
        lambda row: (
            row.factory_id,
            row.product_size_ml,
            _normalized(row.variety),
            _normalized(row.packaging_size_name),
        ),
    )
    metric_groups = _group_duplicates(
        session.query(PackagingMetrics).order_by(PackagingMetrics.id).all(),
        lambda row: (
            row.factory_id,
            row.cup_size_ml,
            _normalized(row.variant_name),
        ),
    )

    tables = {
        "final_product_stock": {
            "duplicate_count": sum(len(group) - 1 for group in final_groups),
            "duplicate_groups": len(final_groups),
            "affected_keys": [_final_product_report(group) for group in final_groups],
        },
        "packaging_metrics": {
            "duplicate_count": sum(len(group) - 1 for group in metric_groups),
            "duplicate_groups": len(metric_groups),
            "affected_keys": [_packaging_metrics_report(group) for group in metric_groups],
        },
    }
    return {
        "mode": "dry-run",
        "total_duplicate_count": sum(table["duplicate_count"] for table in tables.values()),
        "tables": tables,
    }


def _apply_final_product_merge(session, detail: dict[str, Any]) -> None:
    merge = detail["suggested_merge"]
    rows = {
        row.id: row
        for row in session.query(FinalProductStock)
        .filter(FinalProductStock.id.in_(detail["row_ids"]))
        .all()
    }
    survivor = rows[merge["survivor_id"]]
    result = merge["result"]
    survivor.current_quantity = result["current_quantity"]
    survivor.total_boxes = result["total_boxes"]
    survivor.loose_packets = result["loose_packets"]
    survivor.pieces_per_packet = result["pieces_per_packet"]
    survivor.packets_per_box_limit = result["packets_per_box_limit"]
    for row_id in merge["delete_ids"]:
        session.delete(rows[row_id])


def _apply_packaging_metrics_merge(session, detail: dict[str, Any]) -> None:
    merge = detail["suggested_merge"]
    rows = {
        row.id: row
        for row in session.query(PackagingMetrics)
        .filter(PackagingMetrics.id.in_(detail["row_ids"]))
        .all()
    }
    survivor = rows[merge["survivor_id"]]
    source = rows[merge["value_source_id"]]
    survivor.kg_per_box = source.kg_per_box
    survivor.cups_per_box = source.cups_per_box
    for row_id in merge["delete_ids"]:
        session.delete(rows[row_id])


def run_dedupe(session, *, apply: bool = False) -> dict[str, Any]:
    report = build_dedupe_report(session)
    if not apply:
        return report

    for detail in report["tables"]["final_product_stock"]["affected_keys"]:
        _apply_final_product_merge(session, detail)
    for detail in report["tables"]["packaging_metrics"]["affected_keys"]:
        _apply_packaging_metrics_merge(session, detail)

    session.commit()
    report["mode"] = "apply"
    report["applied_duplicate_count"] = report["total_duplicate_count"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect and optionally merge T1.2 duplicates without changing schema."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the suggested merges in one transaction. Default is dry-run.",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        report = run_dedupe(session, apply=args.apply)
        print(json.dumps(report, indent=2, default=_serialize, sort_keys=True))
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
