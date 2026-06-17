from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from db import SessionLocal, engine  # noqa: E402
from services.finished_goods_cleanup import (  # noqa: E402
    dry_run_auto_generated_finished_goods,
    remove_auto_generated_finished_goods,
)


PATTERN_SQL = """
(
    lower(coalesce({expr}, '')) like '%plain white%'
    or lower(coalesce({expr}, '')) like '%white cup%'
)
"""


TABLE_SPECS = {
    "final_product_stock": {
        "identity": ["id", "factory_id"],
        "text": ["product_restore_key", "variety", "packaging_size_name", "carton_type", "source"],
        "optional": ["created_at", "updated_at", "source", "is_auto_created", "is_active", "archived_at"],
    },
    "finished_goods_stock": {
        "identity": ["id", "factory_id"],
        "text": ["variant_name", "category"],
        "optional": ["updated_at"],
    },
    "packaging_profiles": {
        "identity": ["id", "factory_id"],
        "text": ["product_name", "print_design_name", "profile_name", "box_size_name"],
        "optional": [],
    },
    "inventory": {
        "identity": ["id", "factory_id"],
        "text": ["item_name", "category", "packaging_size"],
        "optional": [],
    },
}


def _existing_columns(table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def _select_diagnostic_rows(factory_id: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with engine.connect() as conn:
        inspector = inspect(conn)
        for table_name, spec in TABLE_SPECS.items():
            if not inspector.has_table(table_name):
                continue
            columns = _existing_columns(table_name)
            text_columns = [column for column in spec["text"] if column in columns]
            if not text_columns:
                continue
            selected = []
            for column in [*spec["identity"], *spec["text"], *spec["optional"]]:
                if column in columns and column not in selected:
                    selected.append(column)
            where_parts = [
                "(" + " OR ".join(
                    PATTERN_SQL.format(expr=column).strip()
                    for column in text_columns
                ) + ")"
            ]
            params: dict[str, Any] = {}
            if factory_id is not None and "factory_id" in columns:
                where_parts.append("factory_id = :factory_id")
                params["factory_id"] = str(factory_id)
            sql = text(
                f"SELECT {', '.join(selected)} FROM {table_name} "
                f"WHERE {' AND '.join(where_parts)} ORDER BY id"
            )
            for result in conn.execute(sql, params).mappings():
                item = {"table_name": table_name}
                item.update(dict(result))
                rows.append(item)
    return rows


def _print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No Plain White / White Cup rows found.")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose and clean auto-generated Plain White finished goods variants.")
    parser.add_argument("--factory-id", required=True, help="Factory ID to inspect/clean.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print diagnostic and cleanup report only.")
    mode.add_argument("--apply", action="store_true", help="Archive safe-to-remove final_product_stock rows.")
    args = parser.parse_args()

    try:
        print("Diagnostic rows:")
        diagnostic_rows = _select_diagnostic_rows(args.factory_id)
        _print_rows(diagnostic_rows)

        db = SessionLocal()
        if args.apply:
            cleanup_rows = remove_auto_generated_finished_goods(db, factory_id=args.factory_id)
            db.commit()
        else:
            cleanup_rows = dry_run_auto_generated_finished_goods(db, factory_id=args.factory_id)
        print("\nCleanup report:")
        _print_rows([row.__dict__ for row in cleanup_rows])
        removable = sum(1 for row in cleanup_rows if row.safe_to_remove)
        print(f"\nSafe-to-remove rows: {removable}")
        print(f"Mode: {'apply' if args.apply else 'dry-run'}")
        db.close()
    except SQLAlchemyError as exc:
        print(f"Database connection/query failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2
    except Exception:
        if "db" in locals():
            db.rollback()
        raise
    finally:
        if "db" in locals():
            db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
