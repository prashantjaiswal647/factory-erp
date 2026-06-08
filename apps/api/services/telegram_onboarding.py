from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    AttendanceLog,
    Customer,
    DailyProduction,
    DailySale,
    Factory,
    FactoryExpense,
    Inventory,
    Machine,
    Payment,
    TelegramUserBinding,
    User,
)


OWNER_MENU = [
    [("📊 Today Summary", "owner_today_summary"), ("🏭 Production Status", "owner_production_status")],
    [("📦 Inventory Alert", "owner_inventory_alert"), ("💰 Due Payments", "owner_due_payments")],
    [("👥 Staff Actions", "owner_staff_actions"), ("🧪 Test Message", "telegram_test_message")],
]
SUB_OWNER_MENU = [
    [("📊 Today Summary", "subowner_today_summary"), ("🏭 Production Status", "subowner_production_status")],
    [("📦 Inventory Alert", "subowner_inventory_alert"), ("💰 Payment Summary", "subowner_payment_summary")],
    [("🧪 Test Message", "telegram_test_message")],
]


def role_menu(role: str) -> list[list[tuple[str, str]]]:
    return OWNER_MENU if role == "Owner" else SUB_OWNER_MENU if role == "Sub-Owner" else []


def inline_keyboard(role: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": callback_data} for text, callback_data in row]
            for row in role_menu(role)
        ]
    }


def render_welcome_message(factory: Factory, user: User, binding: TelegramUserBinding) -> str:
    username = f"@{binding.telegram_username}" if binding.telegram_username else "Connected account"
    if user.role == "Owner":
        return (
            "✅ Munshi AI Telegram Connected\n\n"
            f"नमस्ते {user.full_name or user.username} ji,\n"
            "आपकी factory Telegram से successfully connect हो गई है.\n\n"
            "🏭 Factory Details\n"
            f"Factory: {factory.name}\nRole: Owner\nFactory ID: {factory.id}\nConnected Telegram: {username}\n\n"
            "📌 Munshi AI आपको क्या भेजेगा?\n"
            "• Daily Morning Briefing\n• Production Summary\n• Inventory Alerts\n• Sales & Payment Updates\n"
            "• Outstanding Recovery Alerts\n• Staff Activity Alerts\n• Factory Health Alerts\n• Weekly Business Digest\n\n"
            "⏰ Daily Updates\nMorning Briefing: रोज सुबह 9:00 AM\nWeekly Digest: हर रविवार 7:00 PM\nCritical Alerts: तुरंत\n\n"
            "🔔 Sub Owner या Supervisor के important dashboard actions की सूचना आपको मिलेगी.\n\n"
            "आपका Telegram setup complete है ✅"
        )
    return (
        "✅ Munshi AI Telegram Connected\n\n"
        f"नमस्ते {user.full_name or user.username} ji,\n"
        "आपका Telegram Munshi AI से successfully connect हो गया है.\n\n"
        "🏭 Factory Details\n"
        f"Factory: {factory.name}\nRole: Sub Owner\nConnected Telegram: {username}\n\n"
        "📌 आपको क्या मिलेगा?\n"
        "• Daily Factory Briefing\n• Production Updates\n• Inventory Updates\n• Performance Summary\n"
        "• Assigned Alerts\n• Outstanding Summary (if enabled)\n\n"
        "⏰ Daily Updates\nMorning Briefing: रोज सुबह 9:00 AM\nCritical Alerts: आवश्यक होने पर तुरंत\n\n"
        "ℹ️ Owner के dashboard actions आपको Telegram पर नहीं भेजे जाएंगे.\n"
        "आपके या Supervisor के important actions Owner को notify किए जा सकते हैं.\n\n"
        "आपका Telegram setup complete है ✅"
    )


def _money(value) -> str:
    return f"₹{Decimal(str(value or 0)):,.2f}"


def render_callback_response(db: Session, binding: TelegramUserBinding, callback_data: str) -> str:
    factory_id = binding.factory_id
    today = date.today()
    if callback_data == "telegram_test_message":
        return "✅ Telegram test successful.\n\nMunshi AI alerts are active."

    if callback_data.endswith("today_summary"):
        production = db.query(func.sum(DailyProduction.total_boxes_made)).filter(
            DailyProduction.factory_id == factory_id, DailyProduction.date == today
        ).scalar()
        sales = db.query(func.sum(DailySale.total_amount)).filter(
            DailySale.factory_id == factory_id, DailySale.date == today
        ).scalar()
        collections = db.query(func.sum(Payment.amount_paid)).filter(
            Payment.factory_id == factory_id, Payment.date == today
        ).scalar()
        expenses = db.query(func.sum(FactoryExpense.amount)).filter(
            FactoryExpense.factory_id == factory_id, func.date(FactoryExpense.timestamp) == today
        ).scalar()
        if all(value is None for value in (production, sales, collections, expenses)):
            return "📊 Today Summary\n\nअभी इस section का data available नहीं है."
        return (
            "📊 Today Summary\n\n"
            f"Production: {int(production or 0):,}\nSales: {_money(sales)}\n"
            f"Collection: {_money(collections)}\nExpenses: {_money(expenses)}\n"
            f"Net Snapshot: {_money(Decimal(str(sales or 0)) - Decimal(str(expenses or 0)))}"
        )

    if callback_data.endswith("production_status"):
        active = db.query(Machine).filter(Machine.factory_id == factory_id, Machine.is_active.is_(True)).count()
        inactive = db.query(Machine).filter(Machine.factory_id == factory_id, Machine.is_active.is_(False)).count()
        production = db.query(func.sum(DailyProduction.total_boxes_made)).filter(
            DailyProduction.factory_id == factory_id, DailyProduction.date == today
        ).scalar()
        return f"🏭 Production Status\n\nActive Machines: {active}\nInactive Machines: {inactive}\nToday's Production: {int(production or 0):,}"

    if callback_data.endswith("inventory_alert"):
        low_items = db.query(Inventory).filter(
            Inventory.factory_id == factory_id, Inventory.quantity <= 0
        ).limit(5).all()
        if not low_items:
            return "📦 Inventory Alert\n\nअभी कोई low-stock alert नहीं है."
        lines = ["📦 Inventory Alert", "", "Low Stock Items:"]
        lines.extend(f"• {item.item_name}: {item.quantity or 0} {item.unit or ''}" for item in low_items)
        return "\n".join(lines)

    if callback_data.endswith("due_payments") or callback_data.endswith("payment_summary"):
        customers = db.query(Customer).filter(Customer.factory_id == factory_id).order_by(Customer.total_due.desc()).limit(5).all()
        outstanding = sum(Decimal(str(customer.total_due or 0)) for customer in customers)
        collections = db.query(func.sum(Payment.amount_paid)).filter(
            Payment.factory_id == factory_id, Payment.date == today
        ).scalar()
        if not customers and collections is None:
            return "💰 Payment Summary\n\nअभी this section का data available नहीं है."
        lines = ["💰 Payment Summary", "", f"Total Outstanding: {_money(outstanding)}", f"Today's Collection: {_money(collections)}"]
        if customers:
            lines.append("\nTop Due Customers:")
            lines.extend(f"• {customer.name}: {_money(customer.total_due)}" for customer in customers)
        return "\n".join(lines)

    if callback_data == "owner_staff_actions":
        attendance = db.query(AttendanceLog).filter(
            AttendanceLog.factory_id == factory_id, AttendanceLog.date == today
        ).count()
        return f"👥 Staff Actions\n\nAttendance entries today: {attendance}\nRecent role actions dashboard Activity Log में available हैं."

    return "अभी इस section का data available नहीं है."
