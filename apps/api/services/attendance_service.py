from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import AttendanceLog, Worker


ATTENDANCE_STATUSES = (
    "Present",
    "Absent",
    "Weekly Off",
    "Paid Holiday",
    "Paid Leave",
    "Half Day",
)

STATUS_ALIASES = {
    "P": "Present",
    "A": "Absent",
    "WO": "Weekly Off",
    "PH": "Paid Holiday",
    "PL": "Paid Leave",
    "HD": "Half Day",
    "Half-day": "Half Day",
}


def normalize_attendance_status(value: str) -> str:
    normalized = STATUS_ALIASES.get((value or "").strip(), (value or "").strip())
    if normalized not in ATTENDANCE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid attendance status: {value}",
        )
    return normalized


def attendance_units(value: str) -> Decimal:
    normalized = normalize_attendance_status(value)
    if normalized in {"Present", "Weekly Off", "Paid Holiday", "Paid Leave"}:
        return Decimal("1")
    if normalized == "Half Day":
        return Decimal("0.5")
    return Decimal("0")


def upsert_worker_attendance(
    db: Session,
    *,
    factory_id: int | str,
    worker: Worker,
    attendance_date: date,
    attendance_status: str,
    production_qty: Decimal | int | None = None,
) -> tuple[AttendanceLog, bool]:
    normalized = normalize_attendance_status(attendance_status)
    log = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.factory_id == factory_id)
        .filter(AttendanceLog.worker_id == worker.id)
        .filter(AttendanceLog.date == attendance_date)
        .first()
    )
    created = log is None
    if log is None:
        log = AttendanceLog(
            factory_id=factory_id,
            worker_id=worker.id,
            date=attendance_date,
        )
        db.add(log)
    if log.is_settled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance already settled",
        )

    duty_hours = float(worker.duty_hours or worker.shift_hours or 8.0)
    log.status = normalized
    log.is_present = normalized in {"Present", "Half Day"}
    log.duty_hours = duty_hours if duty_hours > 0 else 8.0
    if production_qty is not None:
        log.production_qty = Decimal(str(production_qty))
    db.flush()
    return log, created
