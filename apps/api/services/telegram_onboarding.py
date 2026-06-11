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
    [("📊 Today Summary", "owner_today_summary"), ("💰 Collection War Room", "owner_collection_war_room")],
    [("📦 Inventory Risk", "owner_inventory_risk"), ("🏭 Production Status", "owner_production_status")],
    [("📄 Last Invoice", "owner_last_invoice"), ("👥 Staff Today", "owner_staff_today")],
    [("🔄 Refresh Briefing", "owner_refresh_briefing"), ("📜 Briefing History", "owner_briefing_history")],
    [("🧪 Test Message", "telegram_test_message")],
]
SUB_OWNER_MENU = [
    [("📊 Today Summary", "subowner_today_summary"), ("📦 Inventory Risk", "subowner_inventory_risk")],
    [("🏭 Production Status", "subowner_production_status"), ("👥 Staff Today", "subowner_staff_today")],
    [("🔄 Refresh Briefing", "subowner_refresh_briefing"), ("📜 Briefing History", "subowner_briefing_history")],
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


MAIN_MENU = [
    [("📊 Dekho", "menu:view"), ("✍️ Kaam Karo", "menu:action")],
    [("🔔 Alerts", "menu:alerts"), ("⚙️ Settings", "menu:settings")],
]
VIEW_MENU = [
    [("Outstanding", "view:outstanding"), ("Today Production", "view:production")],
    [("Inventory Stock", "view:inventory"), ("Payments Received", "view:payments")],
    [("Expenses", "view:expenses"), ("Attendance", "view:attendance")],
    [("⬅️ Back", "menu:main")],
]
ACTION_MENU = [
    [("Add Payment", "action:payment"), ("Add Production", "action:production")],
    [("Add Expense", "action:expense"), ("Add Inventory", "action:inventory")],
    [("Mark Attendance", "action:attendance"), ("Create Invoice", "action:invoice")],
    [("⬅️ Back", "menu:main")],
]
CONFIRM_MENU = [
    [("✅ Save", "confirm:save"), ("✏️ Edit", "confirm:edit")],
    [("❌ Cancel", "confirm:cancel")],
]


def role_menu(role: str) -> list[list[tuple[str, str]]]:
    return MAIN_MENU if role in {"Owner", "Sub-Owner"} else []


def inline_keyboard(role: str, menu: str = "main") -> dict:
    menu_rows = {
        "main": role_menu(role),
        "view": VIEW_MENU,
        "action": ACTION_MENU,
        "confirm": CONFIRM_MENU,
    }.get(menu, role_menu(role))
    return {
        "inline_keyboard": [
            [{"text": text, "callback_data": callback_data} for text, callback_data in row]
            for row in menu_rows
        ]
    }


def allowed_menu_callbacks(role: str) -> set[str]:
    rows = role_menu(role) + VIEW_MENU + ACTION_MENU + CONFIRM_MENU
    legacy = {
        "telegram_test_message",
        "subowner_today_summary", "subowner_inventory_risk", "subowner_production_status",
        "subowner_staff_today", "subowner_refresh_briefing", "subowner_briefing_history",
    }
    if role == "Owner":
        legacy |= {
            "owner_today_summary", "owner_collection_war_room",
            "owner_inventory_risk", "owner_production_status", "owner_last_invoice",
            "owner_staff_today", "owner_refresh_briefing", "owner_briefing_history",
        }
    return {callback for row in rows for _, callback in row} | legacy


def handle_nested_menu_callback(
    db: Session,
    binding: TelegramUserBinding,
    callback_data: str,
    telegram_user_id: str,
) -> tuple[str, dict]:
    from services.telegram_action_session import create_session, get_session, update_session

    if callback_data == "menu:main":
        create_session(db, binding.factory_id, telegram_user_id, "menu_navigation", "main", {})
        return "Munshi AI main menu", inline_keyboard(binding.role, "main")
    if callback_data == "menu:view":
        create_session(db, binding.factory_id, telegram_user_id, "menu_navigation", "view", {})
        return "📊 Dekho\n\nRead-only factory information choose karein.", inline_keyboard(binding.role, "view")
    if callback_data == "menu:action":
        create_session(db, binding.factory_id, telegram_user_id, "menu_navigation", "action", {})
        return "✍️ Kaam Karo\n\nAction choose karein. Save se pehle confirmation zaroor hoga.", inline_keyboard(binding.role, "action")
    if callback_data == "menu:alerts":
        create_session(db, binding.factory_id, telegram_user_id, "menu_navigation", "alerts", {})
        return "🔔 Alerts\n\nAlert Center navigation placeholder. ERP data change nahi hua.", inline_keyboard(binding.role, "main")
    if callback_data == "menu:settings":
        create_session(db, binding.factory_id, telegram_user_id, "menu_navigation", "settings", {})
        return "⚙️ Settings\n\nSettings navigation placeholder. ERP data change nahi hua.", inline_keyboard(binding.role, "main")
    if callback_data.startswith("view:"):
        label = callback_data.split(":", 1)[1].replace("_", " ").title()
        create_session(db, binding.factory_id, telegram_user_id, "menu_navigation", callback_data, {})
        return f"{label}\n\nRead-only data placeholder. Live data integration next phase mein hogi.", inline_keyboard(binding.role, "view")
    if callback_data.startswith("action:"):
        action = callback_data.split(":", 1)[1]
        create_session(db, binding.factory_id, telegram_user_id, "menu_action", "confirm", {"action": action, "placeholder": True})
        return (
            f"{action.replace('_', ' ').title()}\n\n"
            "Step-by-step input placeholder ready hai.\n"
            "Koi database update abhi nahi hoga. Continue karne se pehle confirm karein."
        ), inline_keyboard(binding.role, "confirm")
    if callback_data.startswith("confirm:"):
        session = get_session(db, binding.factory_id, telegram_user_id, "menu_action")
        if callback_data == "confirm:cancel":
            if session:
                update_session(db, session.session_id, "cancelled", session.payload_json or {}, status="cancelled")
            return "❌ Action cancelled. Koi data save nahi hua.", inline_keyboard(binding.role, "action")
        if callback_data == "confirm:edit":
            return "✏️ Edit placeholder. Input collection next phase mein enable hoga.", inline_keyboard(binding.role, "action")
        return "✅ Save placeholder. Confirmation received, lekin is phase mein database update disabled hai.", inline_keyboard(binding.role, "action")
    return render_callback_response(db, binding, callback_data), inline_keyboard(binding.role, "main")


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
    from models import User as DbUser, OutstandingBill, InvoiceDocument, AdvancePayment, FinalProductStock
    from datetime import timedelta

    # 1. Resolve user and enforce role/factory mapping
    user = db.query(DbUser).filter(
        DbUser.id == binding.user_id,
        DbUser.factory_id == binding.factory_id,
        DbUser.is_active.is_(True),
    ).first()
    if user is None or user.role not in {"Owner", "Sub-Owner"} or user.role != binding.role:
        return "Telegram updates abhi aapke role ke liye enabled nahi hain."

    # 2. Prevent role bypass or mismatched data requests
    if callback_data.startswith("owner_") and user.role != "Owner":
        return "This action is not available for your role"

    factory_id = binding.factory_id
    today = date.today()

    if callback_data == "telegram_test_message":
        return "✅ Telegram test successful.\n\nMunshi AI alerts are active."

    if callback_data.endswith("today_summary"):
        yesterday = today - timedelta(days=1)
        
        prod_today = db.query(func.sum(DailyProduction.total_boxes_made)).filter(
            DailyProduction.factory_id == factory_id, DailyProduction.date == today
        ).scalar()
        sales_today = db.query(func.sum(DailySale.total_amount)).filter(
            DailySale.factory_id == factory_id, DailySale.date == today
        ).scalar()
        col_today = db.query(func.sum(Payment.amount_paid)).filter(
            Payment.factory_id == factory_id, Payment.date == today
        ).scalar()
        exp_today = db.query(func.sum(FactoryExpense.amount)).filter(
            FactoryExpense.factory_id == factory_id, func.date(FactoryExpense.timestamp) == today
        ).scalar()

        prod_yest = db.query(func.sum(DailyProduction.total_boxes_made)).filter(
            DailyProduction.factory_id == factory_id, DailyProduction.date == yesterday
        ).scalar()
        sales_yest = db.query(func.sum(DailySale.total_amount)).filter(
            DailySale.factory_id == factory_id, DailySale.date == yesterday
        ).scalar()
        col_yest = db.query(func.sum(Payment.amount_paid)).filter(
            Payment.factory_id == factory_id, Payment.date == yesterday
        ).scalar()

        if all(v is None for v in (prod_today, sales_today, col_today, exp_today, prod_yest, sales_yest, col_yest)):
            return "📊 Today Summary\n\nAbhi is section ka data available nahi hai."

        lines = [
            "📊 Today Summary",
            f"Date: {today.strftime('%d %b %Y')}",
            "",
            "Aaj Ka Summary:",
            f"• Production: {int(prod_today or 0)} Boxes",
        ]
        if user.role == "Owner":
            lines.extend([
                f"• Sales: {_money(sales_today)}",
                f"• Collection: {_money(col_today)}",
                f"• Expenses: {_money(exp_today)}"
            ])
        lines.append("")
        lines.append("Yesterday Summary:")
        lines.append(f"• Production: {int(prod_yest or 0)} Boxes")
        if user.role == "Owner":
            lines.extend([
                f"• Sales: {_money(sales_yest)}",
                f"• Collection: {_money(col_yest)}"
            ])

        return "\n".join(lines).strip()

    if callback_data == "owner_collection_war_room":
        bills = db.query(OutstandingBill).filter(
            OutstandingBill.factory_id == factory_id,
            OutstandingBill.status.in_(["active", "partial"]),
            OutstandingBill.balance_amount > 0
        ).all()
        if not bills:
            return "💰 Collection War Room\n\nAbhi is section ka data available nahi hai."

        total_outstanding = sum(bill.balance_amount for bill in bills)
        overdue_amount = sum(bill.balance_amount for bill in bills if (today - bill.bill_date).days > 15)

        customer_dues = {}
        for bill in bills:
            c_id = bill.customer_id
            if c_id not in customer_dues:
                customer_dues[c_id] = {
                    "name": bill.customer.name,
                    "due": Decimal("0.00")
                }
            customer_dues[c_id]["due"] += bill.balance_amount

        top_customers = sorted(customer_dues.values(), key=lambda x: x["due"], reverse=True)[:5]

        lines = [
            "💰 Collection War Room",
            "",
            f"Total Outstanding: {_money(total_outstanding)}",
            f"Overdue Amount: {_money(overdue_amount)}",
            "",
            "Top Due Customers:"
        ]
        for idx, tc in enumerate(top_customers, 1):
            lines.append(f"{idx}. {tc['name']}: {_money(tc['due'])}")

        return "\n".join(lines).strip()

    if callback_data.endswith("inventory_risk"):
        low_rm = db.query(Inventory).filter(
            Inventory.factory_id == factory_id, Inventory.quantity <= 0
        ).limit(3).all()
        low_fg = db.query(FinalProductStock).filter(
            FinalProductStock.factory_id == factory_id, FinalProductStock.current_quantity <= 0
        ).limit(3).all()

        if not low_rm and not low_fg:
            return "📦 Inventory Risk\n\nAbhi is section ka data available nahi hai."

        lines = ["📦 Inventory Risk", ""]
        if low_rm:
            lines.append("Raw Materials Risk:")
            lines.extend(f"• {item.item_name}: 0 {item.unit or ''}" for item in low_rm)
            lines.append("")
        if low_fg:
            lines.append("Finished Goods Shortage:")
            lines.extend(f"• {item.product_size_ml}ml {item.variety}: 0 boxes" for item in low_fg)

        return "\n".join(lines).strip()

    if callback_data.endswith("production_status"):
        prod_boxes = db.query(func.sum(DailyProduction.total_boxes_made)).filter(
            DailyProduction.factory_id == factory_id, DailyProduction.date == today
        ).scalar() or 0
        wastage_kg = db.query(func.sum(DailyProduction.wastage_kg)).filter(
            DailyProduction.factory_id == factory_id, DailyProduction.date == today
        ).scalar() or 0.0
        active_machines = db.query(Machine).filter(
            Machine.factory_id == factory_id, Machine.is_active.is_(True)
        ).count()
        total_machines = db.query(Machine).filter(Machine.factory_id == factory_id).count()

        if total_machines == 0 and prod_boxes == 0:
            return "🏭 Production Status\n\nAbhi is section ka data available nahi hai."

        return (
            "🏭 Production Status\n\n"
            f"Today Production: {int(prod_boxes)} Boxes\n"
            f"Active Machines: {active_machines}/{total_machines}\n"
            f"Wastage Today: {float(wastage_kg):.2f} kg"
        ).strip()

    if callback_data == "owner_last_invoice":
        last_inv = db.query(InvoiceDocument).filter(
            InvoiceDocument.factory_id == factory_id
        ).order_by(InvoiceDocument.id.desc()).first()
        if last_inv is None:
            return "📄 Last Invoice\n\nAbhi is section ka data available nahi hai."

        return (
            "📄 Last Invoice\n\n"
            f"Invoice Number: #{last_inv.invoice_number}\n"
            f"Date: {last_inv.invoice_date.strftime('%d %b %Y')}\n"
            f"Customer: {last_inv.customer_name}\n"
            f"Total Amount: {_money(last_inv.bill_total)}\n\n"
            "Download Link:\n"
            f"https://munshiai.co.in/api/invoices/{last_inv.id}/pdf"
        ).strip()

    if callback_data.endswith("staff_today"):
        present_count = db.query(AttendanceLog).filter(
            AttendanceLog.factory_id == factory_id,
            AttendanceLog.date == today,
            AttendanceLog.status == "Present"
        ).count()
        total_attendance = db.query(AttendanceLog).filter(
            AttendanceLog.factory_id == factory_id,
            AttendanceLog.date == today
        ).count()
        advances_today = db.query(func.sum(AdvancePayment.amount)).filter(
            AdvancePayment.factory_id == factory_id,
            AdvancePayment.date == today
        ).scalar() or 0.0

        if total_attendance == 0 and advances_today == 0:
            return "👥 Staff Today\n\nAbhi is section ka data available nahi hai."

        lines = [
            "👥 Staff Today",
            "",
            f"• Present Workers: {present_count}",
            f"• Total Attendance Entries: {total_attendance}"
        ]
        if user.role == "Owner":
            lines.append(f"• Today's Advance: {_money(advances_today)}")

        return "\n".join(lines).strip()

    if callback_data.endswith("refresh_briefing"):
        from services.briefing_recovery_merge import compose_daily_briefing_with_recovery
        res = compose_daily_briefing_with_recovery(db, factory_id, today, user)
        return res["message_text"]

    if callback_data.endswith("briefing_history"):
        from models import BriefingSnapshot
        from datetime import timedelta
        cutoff = today - timedelta(days=7)
        # Fetch last 7 briefings for this factory & user's role
        query = db.query(BriefingSnapshot).filter(
            BriefingSnapshot.factory_id == factory_id,
            BriefingSnapshot.role == user.role,
            BriefingSnapshot.briefing_date >= cutoff
        )
        if user.role == "Sub-Owner":
            query = query.filter(BriefingSnapshot.user_id == user.id)
            
        snapshots = query.order_by(BriefingSnapshot.briefing_date.desc()).all()
        if not snapshots:
            return "📜 Briefing History\n\nAbhi is section ka data available nahi hai."
            
        lines = ["📜 Last 7 briefings summary:", ""]
        for s in snapshots:
            date_str = s.briefing_date.strftime("%d %b")
            score_str = f"Health {int(s.health_score)}" if s.health_score is not None else "Health --"
            
            # Extract metrics
            js = s.snapshot_json or {}
            snap = js.get("snapshot") or {}
            rec = js.get("recovery_snapshot") or {}
            
            if user.role == "Owner":
                col_val = float(rec.get("yesterday_collections_paise", 0)) / 100.0
                out_val = snap.get("sales", {}).get("outstanding_amount", 0) or 0
                
                # Format to short compact currency
                def short_money(v):
                    if v >= 100000:
                        return f"₹{v/100000:.1f}L"
                    if v >= 1000:
                        return f"₹{v/1000:.0f}k"
                    return f"₹{v}"
                    
                lines.append(f"{date_str} — {score_str} — Collection {short_money(col_val)} — Outstanding {short_money(out_val)}")
            else:
                # Sub-Owner variant: Operational metrics only (no financial details)
                prod_val = snap.get("production", {}).get("total_boxes", 0) or 0
                lines.append(f"{date_str} — {score_str} — Production {prod_val} boxes")
                
        return "\n".join(lines).strip()

    return "Abhi is section ka data available nahi hai."
