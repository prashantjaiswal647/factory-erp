from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parent
API_DIR = ROOT_DIR / "apps" / "api"
if not API_DIR.exists():
    API_DIR = ROOT_DIR if (ROOT_DIR / "main.py").exists() else Path.cwd()
sys.path.insert(0, str(API_DIR))

from db import SessionLocal
from main import ensure_runtime_schema
from routers.operations import list_sequence_logs, log_factory_operation


LOCAL_TZ = ZoneInfo("Asia/Kolkata")


def main() -> None:
    ensure_runtime_schema()
    db = SessionLocal()
    try:
        factory_name = "Activity Log Verification Factory"
        factory_id = db.execute(
            text(
                """
                INSERT INTO factories (name)
                VALUES (:name)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """
            ),
            {"name": factory_name},
        ).scalar_one()

        marker = datetime.now(LOCAL_TZ).strftime("%Y%m%d%H%M%S")
        log_factory_operation(
            db,
            factory_id=int(factory_id),
            event_type="payment",
            description=f"💰 Sale Logged: Sold 3 boxes to Test Customer {marker} - Value: ₹1,500.00",
        )
        log_factory_operation(
            db,
            factory_id=int(factory_id),
            event_type="production",
            description=f"📦 Production Update: Machine QA-1 completed 8 boxes of 210 cups (Wastage: 1.50%) [{marker}]",
        )
        db.commit()

        current_user = SimpleNamespace(factory_id=int(factory_id))
        rows = list_sequence_logs(
            date=datetime.now(LOCAL_TZ).date().isoformat(),
            current_user=current_user,
            db=db,
        )

        matching = [row for row in rows if marker in row["description"]]
        assert len(matching) == 2, f"Expected 2 verification logs, found {len(matching)}"
        created_values = [row["created_at"] for row in matching]
        assert created_values == sorted(created_values, reverse=True), "Logs are not sorted newest first"
        assert all(row.get("created_time") for row in matching), "created_time HH:MM AM/PM missing"

        print("activity log verification passed")
        for row in matching:
            print(f"{row['created_time']} | {row['event_type']} | {row['description']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
