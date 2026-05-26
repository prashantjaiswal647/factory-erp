from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from dependencies import PAYMENT_ROLES, check_permissions
from db import get_db
from models import AdvancePayment, AttendanceLog, HisabSettlement, User, Worker, WorkerOpeningAttendance
from schemas import OpeningAttendanceResponse


router = APIRouter(prefix="/api/workers", tags=["attendance-ledger"])
MONEY_QUANT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def month_bounds(month: str) -> tuple[date, date]:
    try:
        year, month_number = [int(part) for part in month.split("-")]
        return date(year, month_number, 1), date(year, month_number, monthrange(year, month_number)[1])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Month must be YYYY-MM") from exc


def attendance_units(status: str) -> Decimal:
    if status == "Present":
        return Decimal("1")
    if status == "Half-day":
        return Decimal("0.5")
    return Decimal("0")


def worker_rate(worker: Worker) -> Decimal:
    return money(worker.daily_wage_rate or worker.daily_wages or worker.daily_salary or worker.salary or 0)


def get_worker(db: Session, factory_id: int, worker_id: int) -> Worker:
    worker = (
        db.query(Worker)
        .filter(Worker.factory_id == factory_id)
        .filter(Worker.id == worker_id)
        .filter(Worker.is_active.is_(True))
        .first()
    )
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")
    return worker


class AttendanceSummaryRow(BaseModel):
    worker_id: int
    worker_name: str
    phone: Optional[str] = None
    daily_wage_rate: Decimal
    previous_attendance: int = 0
    duty_days: Decimal
    uncleared_advance: Decimal
    net_current_balance: Decimal


class AttendanceSummaryResponse(BaseModel):
    month: str
    workers: List[AttendanceSummaryRow]


class DayLedgerRow(BaseModel):
    date: date
    attendance_id: Optional[int] = None
    status: str = "Absent"
    production_qty: Optional[Decimal] = None
    duty_amount: Decimal
    advance_amount: Decimal


class WorkerLedgerResponse(BaseModel):
    worker_id: int
    worker_name: str
    month: str
    days: List[DayLedgerRow]
    opening_attendance: Optional[OpeningAttendanceResponse] = None


class AttendanceUpsert(BaseModel):
    date: date
    status: str = Field(..., pattern="^(Present|Absent|Half-day)$")
    production_qty: Optional[Decimal] = Field(default=None, ge=0)


class AdvanceCreate(BaseModel):
    date: date
    amount: Decimal = Field(..., gt=0)


class SettlementRequest(BaseModel):
    worker_id: int = Field(..., gt=0)
    duty_from_date: date
    duty_to_date: date
    advance_cutoff_date: date
    confirm: bool = False


class SettlementResponse(BaseModel):
    worker_id: int
    total_duty_amount: Decimal
    total_advance_deducted: Decimal
    net_payable: Decimal
    settlement_id: Optional[int] = None
    attendance_count: int
    advance_count: int


@router.get("/attendance/summary", response_model=AttendanceSummaryResponse)
def attendance_summary(
    month: str,
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    start, end = month_bounds(month)
    rows: list[AttendanceSummaryRow] = []
    workers = (
        db.query(Worker)
        .filter(Worker.factory_id == current_user.factory_id)
        .filter(Worker.is_active.is_(True))
        .order_by(Worker.name.asc())
        .all()
    )
    for worker in workers:
        opening_att = (
            db.query(WorkerOpeningAttendance)
            .filter(WorkerOpeningAttendance.factory_id == current_user.factory_id)
            .filter(WorkerOpeningAttendance.worker_id == worker.id)
            .first()
        )
        
        opening_payable_days = Decimal("0")
        opening_advance = Decimal("0")
        opening_deductions = Decimal("0")
        opening_ot_hours = Decimal("0")
        overlap_present = False
        
        if opening_att is not None:
            # Check if settled
            settled_count = (
                db.query(HisabSettlement)
                .filter(HisabSettlement.factory_id == current_user.factory_id)
                .filter(HisabSettlement.worker_id == worker.id)
                .filter(HisabSettlement.duty_to_date >= opening_att.period_end)
                .count()
            )
            if settled_count == 0:
                # Only include if not settled and overlaps with month
                if opening_att.period_start <= end and opening_att.period_end >= start:
                    overlap_present = True
                    opening_payable_days = Decimal(str(opening_att.present_days or 0)) + \
                                           Decimal(str(opening_att.half_days or 0)) * Decimal("0.5") + \
                                           Decimal(str(opening_att.paid_leave_days or 0))
                    opening_advance = Decimal(str(opening_att.advance_paid or 0))
                    opening_deductions = Decimal(str(opening_att.deductions or 0))
                    opening_ot_hours = Decimal(str(opening_att.overtime_hours or 0))

        # Query daily logs, excluding those overlapping with opening range
        query = (
            db.query(AttendanceLog)
            .filter(AttendanceLog.factory_id == current_user.factory_id)
            .filter(AttendanceLog.worker_id == worker.id)
            .filter(AttendanceLog.date >= start)
            .filter(AttendanceLog.date <= end)
        )
        if opening_att is not None:
            query = query.filter((AttendanceLog.date < opening_att.period_start) | (AttendanceLog.date > opening_att.period_end))
        logs = query.all()
        
        daily_duty_days = sum((attendance_units(log.status) for log in logs), Decimal("0"))
        duty_days = daily_duty_days + opening_payable_days
        
        # Overtime pay
        daily_ot_hours = sum((Decimal(str(log.overtime_hours or 0)) for log in logs), Decimal("0"))
        total_ot_hours = daily_ot_hours + opening_ot_hours
        shift_hours = Decimal(str(worker.shift_hours or 8.0))
        if shift_hours <= 0:
            shift_hours = Decimal("8.0")
        hourly_rate = worker_rate(worker) / shift_hours
        overtime_pay = total_ot_hours * hourly_rate

        advance_total = money(
            db.query(sql_func.coalesce(sql_func.sum(AdvancePayment.amount), 0))
            .filter(AdvancePayment.factory_id == current_user.factory_id)
            .filter(AdvancePayment.worker_id == worker.id)
            .filter(AdvancePayment.is_settled.is_(False))
            .scalar()
        )
        
        if overlap_present:
            advance_total = money(advance_total + opening_advance + opening_deductions)
            
        duty_amount = money((duty_days * worker_rate(worker)) + overtime_pay)
        rows.append(
            AttendanceSummaryRow(
                worker_id=worker.id,
                worker_name=worker.name,
                phone=worker.phone,
                daily_wage_rate=worker_rate(worker),
                previous_attendance=int(opening_att.present_days or 0) if opening_att else 0,
                duty_days=duty_days,
                uncleared_advance=advance_total,
                net_current_balance=money(duty_amount - advance_total),
            )
        )
    return AttendanceSummaryResponse(month=month, workers=rows)


@router.get("/{worker_id}/attendance-ledger", response_model=WorkerLedgerResponse)
def worker_ledger(
    worker_id: int,
    month: str,
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    worker = get_worker(db, current_user.factory_id, worker_id)
    start, end = month_bounds(month)
    logs = {
        log.date: log
        for log in db.query(AttendanceLog)
        .filter(AttendanceLog.factory_id == current_user.factory_id)
        .filter(AttendanceLog.worker_id == worker.id)
        .filter(AttendanceLog.date >= start)
        .filter(AttendanceLog.date <= end)
        .all()
    }
    advances = {
        row.date: money(row.amount)
        for row in db.query(
            AdvancePayment.date,
            sql_func.coalesce(sql_func.sum(AdvancePayment.amount), 0).label("amount"),
        )
        .filter(AdvancePayment.factory_id == current_user.factory_id)
        .filter(AdvancePayment.worker_id == worker.id)
        .filter(AdvancePayment.date >= start)
        .filter(AdvancePayment.date <= end)
        .group_by(AdvancePayment.date)
        .all()
    }
    days: list[DayLedgerRow] = []
    current = start
    while current <= end:
        log = logs.get(current)
        status_value = log.status if log else "Absent"
        days.append(
            DayLedgerRow(
                date=current,
                attendance_id=log.id if log else None,
                status=status_value,
                production_qty=log.production_qty if log else None,
                duty_amount=money(attendance_units(status_value) * worker_rate(worker)),
                advance_amount=advances.get(current, Decimal("0.00")),
            )
        )
        current += timedelta(days=1)
        
    opening_att = (
        db.query(WorkerOpeningAttendance)
        .filter(WorkerOpeningAttendance.factory_id == current_user.factory_id)
        .filter(WorkerOpeningAttendance.worker_id == worker.id)
        .first()
    )
    return WorkerLedgerResponse(
        worker_id=worker.id,
        worker_name=worker.name,
        month=month,
        days=days,
        opening_attendance=opening_att,
    )


@router.post("/{worker_id}/attendance", response_model=DayLedgerRow)
def upsert_attendance(
    worker_id: int,
    payload: AttendanceUpsert,
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    worker = get_worker(db, current_user.factory_id, worker_id)
    log = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.factory_id == current_user.factory_id)
        .filter(AttendanceLog.worker_id == worker.id)
        .filter(AttendanceLog.date == payload.date)
        .first()
    )
    if log is None:
        log = AttendanceLog(factory_id=current_user.factory_id, worker_id=worker.id, date=payload.date)
        db.add(log)
    if log.is_settled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attendance already settled")
    log.status = payload.status
    log.is_present = payload.status in ("Present", "Half-day")
    log.production_qty = payload.production_qty
    db.commit()
    db.refresh(log)
    advance_amount = money(
        db.query(sql_func.coalesce(sql_func.sum(AdvancePayment.amount), 0))
        .filter(AdvancePayment.factory_id == current_user.factory_id)
        .filter(AdvancePayment.worker_id == worker.id)
        .filter(AdvancePayment.date == payload.date)
        .scalar()
    )
    return DayLedgerRow(
        date=log.date,
        attendance_id=log.id,
        status=log.status,
        production_qty=log.production_qty,
        duty_amount=money(attendance_units(log.status) * worker_rate(worker)),
        advance_amount=advance_amount,
    )


@router.post("/{worker_id}/advance")
def add_worker_advance(
    worker_id: int,
    payload: AdvanceCreate,
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    worker = get_worker(db, current_user.factory_id, worker_id)
    advance = AdvancePayment(
        factory_id=current_user.factory_id,
        worker_id=worker.id,
        date=payload.date,
        amount=float(payload.amount),
        is_settled=False,
    )
    db.add(advance)
    db.commit()
    db.refresh(advance)
    return {"id": advance.id, "worker_id": worker.id, "date": advance.date, "amount": advance.amount}


def calculate_settlement(db: Session, factory_id: int, worker: Worker, payload: SettlementRequest) -> SettlementResponse:
    if payload.duty_to_date < payload.duty_from_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Duty To cannot be before Duty From")
    
    opening_att = (
        db.query(WorkerOpeningAttendance)
        .filter(WorkerOpeningAttendance.factory_id == factory_id)
        .filter(WorkerOpeningAttendance.worker_id == worker.id)
        .first()
    )

    opening_payable_days = Decimal("0")
    opening_advance = Decimal("0")
    opening_deductions = Decimal("0")
    opening_ot_hours = Decimal("0")
    overlap_present = False

    if opening_att is not None:
        # Check if settled
        settled_count = (
            db.query(HisabSettlement)
            .filter(HisabSettlement.factory_id == factory_id)
            .filter(HisabSettlement.worker_id == worker.id)
            .filter(HisabSettlement.duty_to_date >= opening_att.period_end)
            .count()
        )
        if settled_count == 0:
            if opening_att.period_start <= payload.duty_to_date and opening_att.period_end >= payload.duty_from_date:
                overlap_present = True
                opening_payable_days = Decimal(str(opening_att.present_days or 0)) + \
                                       Decimal(str(opening_att.half_days or 0)) * Decimal("0.5") + \
                                       Decimal(str(opening_att.paid_leave_days or 0))
                opening_advance = Decimal(str(opening_att.advance_paid or 0))
                opening_deductions = Decimal(str(opening_att.deductions or 0))
                opening_ot_hours = Decimal(str(opening_att.overtime_hours or 0))

    query = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.factory_id == factory_id)
        .filter(AttendanceLog.worker_id == worker.id)
        .filter(AttendanceLog.is_settled.is_(False))
        .filter(AttendanceLog.date >= payload.duty_from_date)
        .filter(AttendanceLog.date <= payload.duty_to_date)
    )
    if opening_att is not None:
        query = query.filter((AttendanceLog.date < opening_att.period_start) | (AttendanceLog.date > opening_att.period_end))
    attendance_rows = query.all()

    daily_duty_days = sum((attendance_units(row.status) for row in attendance_rows), Decimal("0"))
    total_duty_days = daily_duty_days + opening_payable_days

    # Overtime pay
    daily_ot_hours = sum((Decimal(str(row.overtime_hours or 0)) for row in attendance_rows), Decimal("0"))
    total_ot_hours = daily_ot_hours + opening_ot_hours
    shift_hours = Decimal(str(worker.shift_hours or 8.0))
    if shift_hours <= 0:
        shift_hours = Decimal("8.0")
    hourly_rate = worker_rate(worker) / shift_hours
    overtime_pay = total_ot_hours * hourly_rate

    total_duty = money((total_duty_days * worker_rate(worker)) + overtime_pay)

    advance_query = (
        db.query(AdvancePayment)
        .filter(AdvancePayment.factory_id == factory_id)
        .filter(AdvancePayment.worker_id == worker.id)
        .filter(AdvancePayment.is_settled.is_(False))
        .filter(AdvancePayment.date <= payload.advance_cutoff_date)
    )
    if opening_att is not None:
        advance_query = advance_query.filter((AdvancePayment.date < opening_att.period_start) | (AdvancePayment.date > opening_att.period_end))
    advance_rows = advance_query.all()
    
    daily_advance = sum((Decimal(str(row.amount or 0)) for row in advance_rows), Decimal("0"))
    total_advance = money(daily_advance)
    if overlap_present:
        total_advance = money(daily_advance + opening_advance + opening_deductions)

    return SettlementResponse(
        worker_id=worker.id,
        total_duty_amount=total_duty,
        total_advance_deducted=total_advance,
        net_payable=money(total_duty - total_advance),
        attendance_count=len(attendance_rows),
        advance_count=len(advance_rows),
    )


@router.post("/settle", response_model=SettlementResponse)
def settle_hisab(
    payload: SettlementRequest,
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    worker = get_worker(db, current_user.factory_id, payload.worker_id)
    preview = calculate_settlement(db, current_user.factory_id, worker, payload)
    if not payload.confirm:
        return preview

    attendance_rows = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.factory_id == current_user.factory_id)
        .filter(AttendanceLog.worker_id == worker.id)
        .filter(AttendanceLog.is_settled.is_(False))
        .filter(AttendanceLog.date >= payload.duty_from_date)
        .filter(AttendanceLog.date <= payload.duty_to_date)
        .all()
    )
    advance_rows = (
        db.query(AdvancePayment)
        .filter(AdvancePayment.factory_id == current_user.factory_id)
        .filter(AdvancePayment.worker_id == worker.id)
        .filter(AdvancePayment.is_settled.is_(False))
        .filter(AdvancePayment.date <= payload.advance_cutoff_date)
        .all()
    )
    settlement = HisabSettlement(
        factory_id=current_user.factory_id,
        worker_id=worker.id,
        duty_from_date=payload.duty_from_date,
        duty_to_date=payload.duty_to_date,
        advance_cutoff_date=payload.advance_cutoff_date,
        total_duty_amount=preview.total_duty_amount,
        total_advance_deducted=preview.total_advance_deducted,
        net_paid=preview.net_payable,
    )
    db.add(settlement)
    for row in attendance_rows:
        row.is_settled = True
    for row in advance_rows:
        row.is_settled = True
    db.commit()
    db.refresh(settlement)
    preview.settlement_id = settlement.id
    return preview


# Worker Payroll Summary Schemas & Route
# ---------------------------------------------------------------------------

class OpeningAttendanceSummary(BaseModel):
    period_start: date
    period_end: date
    payable_days: float
    present_days: float
    half_days: float
    absent_days: float
    overtime_hours: float
    advance_paid: float
    deductions: float


class DailyAttendanceSummary(BaseModel):
    payable_days: float
    present_days: float
    half_days: float
    absent_days: float
    overtime_hours: float


class FinalPayrollSummary(BaseModel):
    total_payable_days: float
    gross_salary: float
    overtime_pay: float
    total_advance: float
    total_deductions: float
    net_payable: float


class PayrollSummaryResponse(BaseModel):
    worker_id: int
    worker_name: str
    month: str
    daily_wage_rate: float
    opening_attendance: Optional[OpeningAttendanceSummary] = None
    daily_attendance: DailyAttendanceSummary
    final: FinalPayrollSummary


@router.get("/{worker_id}/payroll-summary", response_model=PayrollSummaryResponse)
def get_worker_payroll_summary(
    worker_id: int,
    month: str,  # YYYY-MM
    current_user: User = Depends(check_permissions(PAYMENT_ROLES)),
    db: Session = Depends(get_db),
):
    worker = get_worker(db, current_user.factory_id, worker_id)
    start, end = month_bounds(month)
    
    opening_att = (
        db.query(WorkerOpeningAttendance)
        .filter(WorkerOpeningAttendance.factory_id == current_user.factory_id)
        .filter(WorkerOpeningAttendance.worker_id == worker.id)
        .first()
    )
    
    opening_summary = None
    opening_payable_days = Decimal("0")
    opening_advance = Decimal("0")
    opening_deductions = Decimal("0")
    opening_ot_hours = Decimal("0")
    overlap_present = False
    
    if opening_att is not None:
        if opening_att.period_start <= end and opening_att.period_end >= start:
            overlap_present = True
            opening_payable_days = Decimal(str(opening_att.present_days or 0)) + \
                                   Decimal(str(opening_att.half_days or 0)) * Decimal("0.5") + \
                                   Decimal(str(opening_att.paid_leave_days or 0))
            opening_advance = Decimal(str(opening_att.advance_paid or 0))
            opening_deductions = Decimal(str(opening_att.deductions or 0))
            opening_ot_hours = Decimal(str(opening_att.overtime_hours or 0))
            
            opening_summary = OpeningAttendanceSummary(
                period_start=opening_att.period_start,
                period_end=opening_att.period_end,
                payable_days=float(opening_payable_days),
                present_days=float(opening_att.present_days or 0),
                half_days=float(opening_att.half_days or 0),
                absent_days=float(opening_att.absent_days or 0),
                overtime_hours=float(opening_att.overtime_hours or 0),
                advance_paid=float(opening_att.advance_paid or 0),
                deductions=float(opening_att.deductions or 0),
            )
            
    # Load daily logs for this month
    query = (
        db.query(AttendanceLog)
        .filter(AttendanceLog.factory_id == current_user.factory_id)
        .filter(AttendanceLog.worker_id == worker.id)
        .filter(AttendanceLog.date >= start)
        .filter(AttendanceLog.date <= end)
    )
    if opening_att is not None:
        query = query.filter((AttendanceLog.date < opening_att.period_start) | (AttendanceLog.date > opening_att.period_end))
    logs = query.all()
    
    daily_present = sum((1 for log in logs if log.status == "Present"))
    daily_half = sum((1 for log in logs if log.status == "Half-day"))
    daily_absent = sum((1 for log in logs if log.status == "Absent"))
    daily_payable_days = sum((attendance_units(log.status) for log in logs), Decimal("0"))
    daily_ot_hours = sum((Decimal(str(log.overtime_hours or 0)) for log in logs), Decimal("0"))
    
    daily_summary = DailyAttendanceSummary(
        payable_days=float(daily_payable_days),
        present_days=float(daily_present),
        half_days=float(daily_half),
        absent_days=float(daily_absent),
        overtime_hours=float(daily_ot_hours),
    )
    
    total_payable_days = daily_payable_days + opening_payable_days
    rate = worker_rate(worker)
    gross_salary = total_payable_days * rate
    
    # Overtime calculation
    total_ot_hours = daily_ot_hours + opening_ot_hours
    shift_hours = Decimal(str(worker.shift_hours or 8.0))
    if shift_hours <= 0:
        shift_hours = Decimal("8.0")
    hourly_rate = rate / shift_hours
    overtime_pay = total_ot_hours * hourly_rate
    
    # Advances
    daily_advance = db.query(sql_func.coalesce(sql_func.sum(AdvancePayment.amount), 0)).filter(
        AdvancePayment.factory_id == current_user.factory_id,
        AdvancePayment.worker_id == worker.id,
        AdvancePayment.date >= start,
        AdvancePayment.date <= end,
    )
    if opening_att is not None:
        daily_advance = daily_advance.filter((AdvancePayment.date < opening_att.period_start) | (AdvancePayment.date > opening_att.period_end))
    daily_advance_total = Decimal(str(daily_advance.scalar()))
    
    total_advance = daily_advance_total
    total_deductions = Decimal("0")
    if overlap_present:
        total_advance = daily_advance_total + opening_advance
        total_deductions = opening_deductions
        
    net_payable = (gross_salary + overtime_pay) - (total_advance + total_deductions)
    
    final_summary = FinalPayrollSummary(
        total_payable_days=float(total_payable_days),
        gross_salary=float(money(gross_salary)),
        overtime_pay=float(money(overtime_pay)),
        total_advance=float(money(total_advance)),
        total_deductions=float(money(total_deductions)),
        net_payable=float(money(net_payable)),
    )
    
    return PayrollSummaryResponse(
        worker_id=worker.id,
        worker_name=worker.name,
        month=month,
        daily_wage_rate=float(rate),
        opening_attendance=opening_summary,
        daily_attendance=daily_summary,
        final=final_summary,
    )

