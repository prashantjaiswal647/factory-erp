from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    AttendanceLog,
    BlankStock,
    BottomStock,
    Customer,
    DailyProduction,
    FactoryExpense,
    FinalProductStock,
    InvoiceDocument,
    Machine,
    OutstandingBill,
    PaymentCollection,
    ShiftWastage,
    TelegramUserBinding,
    User,
    Worker,
)
from services.attendance_service import attendance_units
from services.timezone_utils import get_kolkata_now


READ_CALLBACKS = {
    "read:outstanding",
    "read:today_production",
    "read:inventory",
    "read:payments",
    "read:expenses",
    "read:attendance",
    "read:wastage",
    "read:invoices",
}


def _money(value) -> str:
    return f"₹{Decimal(str(value or 0)):,.2f}"


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _qty(value) -> str:
    return format(_decimal(value).normalize(), "f")


def _limit(rows, size: int = 10):
    return list(rows[:size]), len(rows) > size


def can_read_telegram(
    db: Session,
    factory_id: int,
    telegram_user_id: str,
) -> TelegramUserBinding | None:
    return (
        db.query(TelegramUserBinding)
        .join(User, User.id == TelegramUserBinding.user_id)
        .filter(
            TelegramUserBinding.factory_id == factory_id,
            TelegramUserBinding.telegram_chat_id == str(telegram_user_id),
            TelegramUserBinding.is_active.is_(True),
            User.factory_id == factory_id,
            User.is_active.is_(True),
            User.role.in_(("Owner", "Sub-Owner")),
        )
        .first()
    )


def can_write_telegram(
    db: Session,
    factory_id: int,
    telegram_user_id: str,
    action: str,
) -> bool:
    binding = can_read_telegram(db, factory_id, telegram_user_id)
    return bool(binding and binding.role in {"Owner", "Sub-Owner"})


def read_outstanding(db: Session, factory_id: int) -> str:
    rows = (
        db.query(OutstandingBill, Customer)
        .join(Customer, Customer.id == OutstandingBill.customer_id)
        .filter(
            OutstandingBill.factory_id == factory_id,
            OutstandingBill.status.notin_(("cancelled", "archived")),
            OutstandingBill.balance_amount > 0,
        )
        .order_by(OutstandingBill.balance_amount.desc(), OutstandingBill.bill_date.asc())
        .all()
    )
    if not rows:
        return "Koi outstanding customer nahi mila."
    total = sum((_decimal(bill.balance_amount) for bill, _ in rows), Decimal("0"))
    overdue = sum(
        (_decimal(bill.balance_amount) for bill, _ in rows if (get_kolkata_now().date() - bill.bill_date).days > 15),
        Decimal("0"),
    )
    top, more = _limit(rows)
    lines = [f"💰 Outstanding\nTotal: {_money(total)}\nOverdue: {_money(overdue)}"]
    lines.extend(f"• {customer.name}: {_money(bill.balance_amount)}" for bill, customer in top)
    if more:
        lines.append("Aur entries app dashboard par available hain.")
    return "\n".join(lines)


def read_today_production(db: Session, factory_id: int) -> str:
    today = get_kolkata_now().date()
    rows = (
        db.query(DailyProduction, Machine, Worker)
        .join(Machine, Machine.id == DailyProduction.machine_id)
        .outerjoin(Worker, Worker.id == DailyProduction.worker_id)
        .filter(
            DailyProduction.factory_id == factory_id,
            DailyProduction.date == today,
            DailyProduction.status == "ACTIVE",
        )
        .order_by(DailyProduction.id.desc())
        .all()
    )
    if not rows:
        return "Aaj production entry nahi hui hai."
    boxes = sum(row.total_boxes_made or 0 for row, _, _ in rows)
    loose = sum(row.loose_packets_made or 0 for row, _, _ in rows)
    blank = sum((_decimal(row.blank_used_kg) for row, _, _ in rows), Decimal("0"))
    bottom = sum((_decimal(row.bottom_used_kg) for row, _, _ in rows), Decimal("0"))
    top, more = _limit(rows)
    lines = [
        f"🏭 Today Production ({today})",
        f"Finished goods added: {boxes} boxes, {loose} packets",
        f"Blank deducted: {_qty(blank)} kg | Bottom: {_qty(bottom)} kg",
    ]
    lines.extend(
        f"• {machine.name}: {worker.name if worker else 'Worker'} - "
        f"{row.total_boxes_made} box, {row.loose_packets_made} packet"
        for row, machine, worker in top
    )
    if more:
        lines.append("Aur production rows dashboard par available hain.")
    return "\n".join(lines)


def read_inventory(db: Session, factory_id: int) -> str:
    blanks = db.query(BlankStock).filter(BlankStock.factory_id == factory_id).order_by(BlankStock.total_qty_kg.asc()).all()
    bottoms = db.query(BottomStock).filter(BottomStock.factory_id == factory_id).order_by(BottomStock.total_weight_kg.asc()).all()
    finished = db.query(FinalProductStock).filter(FinalProductStock.factory_id == factory_id).order_by(FinalProductStock.current_quantity.asc()).all()
    if not blanks and not bottoms and not finished:
        return "Stock data abhi empty hai."
    rows = []
    rows.extend((f"Blank {row.blank_size_ml}ml {row.variety}", _decimal(row.total_qty_kg), "kg") for row in blanks)
    rows.extend((f"Bottom {row.bottom_size_mm}mm {row.variety}", _decimal(row.total_weight_kg), "kg") for row in bottoms)
    rows.extend((f"FG {row.product_size_ml}ml {row.variety}", Decimal(row.current_quantity or 0), "box") for row in finished)
    out_count = sum(1 for _, qty, _ in rows if qty <= 0)
    low_count = sum(1 for _, qty, _ in rows if Decimal("0") < qty <= Decimal("10"))
    top, more = _limit(rows)
    lines = [f"📦 Inventory Stock\nItems: {len(rows)} | Low: {low_count} | Out: {out_count}"]
    lines.extend(f"• {name}: {_qty(qty)} {unit}" for name, qty, unit in top)
    if more:
        lines.append("View more: Munshi AI Inventory dashboard.")
    return "\n".join(lines)


def read_payments(db: Session, factory_id: int) -> str:
    today = get_kolkata_now().date()
    week_start = today - timedelta(days=6)
    rows = (
        db.query(PaymentCollection, Customer)
        .join(Customer, Customer.id == PaymentCollection.customer_id)
        .filter(PaymentCollection.factory_id == factory_id, PaymentCollection.collection_date >= week_start)
        .order_by(PaymentCollection.collection_date.desc(), PaymentCollection.id.desc())
        .all()
    )
    today_total = sum((_decimal(row.amount_collected) for row, _ in rows if row.collection_date == today), Decimal("0"))
    week_total = sum((_decimal(row.amount_collected) for row, _ in rows), Decimal("0"))
    if not rows:
        return f"Payments Received\nToday: {_money(0)}\nLast 7 days: {_money(0)}\nKoi payment entry nahi mili."
    top, more = _limit(rows)
    lines = [f"💳 Payments Received\nToday: {_money(today_total)}\nLast 7 days: {_money(week_total)}"]
    lines.extend(f"• {row.collection_date} {customer.name}: {_money(row.amount_collected)}" for row, customer in top)
    if more:
        lines.append("Aur payment entries dashboard par available hain.")
    return "\n".join(lines)


def read_expenses(db: Session, factory_id: int) -> str:
    today = get_kolkata_now().date()
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)
    rows = db.query(FactoryExpense).filter(
        FactoryExpense.factory_id == factory_id,
        func.date(FactoryExpense.timestamp) >= month_start,
    ).all()
    if not rows:
        return "Expenses\nIs month koi expense entry nahi mili."
    today_total = sum((_decimal(row.amount) for row in rows if row.timestamp.date() == today), Decimal("0"))
    week_total = sum((_decimal(row.amount) for row in rows if row.timestamp.date() >= week_start), Decimal("0"))
    month_total = sum((_decimal(row.amount) for row in rows), Decimal("0"))
    categories: dict[str, Decimal] = {}
    for row in rows:
        categories[row.category] = categories.get(row.category, Decimal("0")) + _decimal(row.amount)
    top, more = _limit(sorted(categories.items(), key=lambda item: item[1], reverse=True))
    lines = [f"🧾 Expenses\nToday: {_money(today_total)}\nWeek: {_money(week_total)}\nMonth: {_money(month_total)}"]
    lines.extend(f"• {category}: {_money(amount)}" for category, amount in top)
    if more:
        lines.append("Aur categories dashboard par available hain.")
    return "\n".join(lines)


def read_attendance(db: Session, factory_id: int) -> str:
    today = get_kolkata_now().date()
    rows = db.query(AttendanceLog).filter(AttendanceLog.factory_id == factory_id, AttendanceLog.date == today).all()
    if not rows:
        return "Attendance\nAaj attendance mark nahi hui hai."
    counts: dict[str, int] = {}
    payable = Decimal("0")
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
        payable += attendance_units(row.status)
    lines = [f"👥 Attendance ({today})", f"Payable attendance: {_qty(payable)}"]
    lines.extend(f"• {status}: {count}" for status, count in sorted(counts.items()))
    return "\n".join(lines)


def read_wastage(db: Session, factory_id: int) -> str:
    today = get_kolkata_now().date()
    rows = db.query(ShiftWastage).filter(ShiftWastage.factory_id == factory_id, ShiftWastage.date == today).all()
    if not rows:
        return "Day/Night Wastage\nAaj wastage entry nahi hui hai."
    day = sum((_decimal(row.wastage_kg) for row in rows if row.shift.lower() == "day"), Decimal("0"))
    night = sum((_decimal(row.wastage_kg) for row in rows if row.shift.lower() == "night"), Decimal("0"))
    notes = [row.note for row in rows if row.note]
    lines = [f"⚠️ Day/Night Wastage\nDay: {_qty(day)} kg\nNight: {_qty(night)} kg\nTotal: {_qty(day + night)} kg"]
    lines.extend(f"• Note: {note}" for note in notes[:10])
    return "\n".join(lines)


def read_invoices(db: Session, factory_id: int) -> str:
    rows = (
        db.query(InvoiceDocument)
        .filter(InvoiceDocument.factory_id == factory_id, InvoiceDocument.status != "archived")
        .order_by(InvoiceDocument.invoice_date.desc(), InvoiceDocument.id.desc())
        .all()
    )
    if not rows:
        return "Invoice Summary\nKoi invoice generate nahi hua hai."
    cancelled = sum(1 for row in rows if row.status == "cancelled")
    outstanding = sum((_decimal(row.customer_total_due) for row in rows if row.status != "cancelled"), Decimal("0"))
    top, more = _limit(rows)
    lines = [
        f"📄 Invoice Summary\nTotal invoices: {len(rows)}\nCancelled: {cancelled}\nInvoice outstanding: {_money(outstanding)}"
    ]
    lines.extend(
        f"• {row.invoice_number} | {row.customer_name} | {_money(row.bill_total)} | {row.status}"
        for row in top
    )
    if more:
        lines.append("View more: Munshi AI Invoice History.")
    return "\n".join(lines)


READ_HANDLERS = {
    "read:outstanding": read_outstanding,
    "read:today_production": read_today_production,
    "read:inventory": read_inventory,
    "read:payments": read_payments,
    "read:expenses": read_expenses,
    "read:attendance": read_attendance,
    "read:wastage": read_wastage,
    "read:invoices": read_invoices,
}


def render_telegram_read(db: Session, factory_id: int, callback_data: str) -> str:
    handler = READ_HANDLERS.get(callback_data)
    if handler is None:
        return "Yeh Telegram option available nahi hai."
    return handler(db, factory_id)
