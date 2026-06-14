from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import AttendanceLog, Factory, Worker
from routers.attendance import (
    AttendanceUpsert,
    BulkWeeklyOffRequest,
    get_worker_payroll_summary,
    mark_all_active_workers_weekly_off,
    upsert_attendance,
)
from routers.operations import mark_worker_present_for_production


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db):
    factory = Factory(name="Attendance Factory")
    db.add(factory)
    db.flush()
    workers = [
        Worker(factory_id=factory.id, name="Worker A", daily_wage_rate=Decimal("500")),
        Worker(factory_id=factory.id, name="Worker B", daily_wage_rate=Decimal("400")),
    ]
    db.add_all(workers)
    db.commit()
    return factory, workers


def _owner(factory_id):
    return SimpleNamespace(
        id=1,
        factory_id=factory_id,
        role="Owner",
        username="owner",
        full_name="Owner",
    )


def test_sunday_and_backdated_weekly_off_without_production_is_payable():
    db = _session()
    factory, workers = _seed(db)
    weekly_off_date = date(2026, 6, 7)

    result = mark_all_active_workers_weekly_off(
        BulkWeeklyOffRequest(date=weekly_off_date),
        current_user=_owner(factory.id),
        db=db,
    )

    assert result.workers_updated == 2
    assert db.query(AttendanceLog).filter_by(date=weekly_off_date).count() == 2
    payroll = get_worker_payroll_summary(
        workers[0].id,
        "2026-06",
        current_user=_owner(factory.id),
        db=db,
    )
    assert payroll.final.total_payable_days == 1
    assert payroll.final.gross_salary == 500


def test_attendance_upsert_and_production_do_not_duplicate_rows():
    db = _session()
    factory, workers = _seed(db)
    attendance_date = date(2026, 6, 8)

    upsert_attendance(
        workers[0].id,
        AttendanceUpsert(date=attendance_date, status="Paid Leave"),
        BackgroundTasks(),
        current_user=_owner(factory.id),
        db=db,
    )
    upsert_attendance(
        workers[0].id,
        AttendanceUpsert(date=attendance_date, status="Absent"),
        BackgroundTasks(),
        current_user=_owner(factory.id),
        db=db,
    )
    production_log = mark_worker_present_for_production(
        db,
        factory_id=str(factory.id),
        worker=workers[0],
        production_date=attendance_date,
        production_qty=120,
    )
    db.commit()

    rows = db.query(AttendanceLog).filter_by(
        factory_id=factory.id,
        worker_id=workers[0].id,
        date=attendance_date,
    ).all()
    assert len(rows) == 1
    assert production_log.status == "Present"
    assert production_log.production_qty == Decimal("120")
