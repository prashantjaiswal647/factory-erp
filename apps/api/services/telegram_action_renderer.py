from decimal import Decimal
from typing import List, Any

def format_outstanding_for_telegram(outstanding_data: Any) -> str:
    """Format top 5 outstanding customer balances for Telegram."""
    grand_total = getattr(outstanding_data, "grand_total_outstanding", Decimal("0.00"))
    customers = getattr(outstanding_data, "customers", []) or []

    # Sort by balance descending
    sorted_customers = sorted(
        customers,
        key=lambda c: getattr(c, "current_pending_balance", Decimal("0.00")),
        reverse=True
    )

    lines = [
        "💵 *Outstanding Balances*",
        f"Total Outstanding: ₹{grand_total:,.2f}",
        "",
        "*Top Customers:*",
    ]

    for idx, c in enumerate(sorted_customers[:5], 1):
        lines.append(f"{idx}. *{c.customer_name}*: ₹{c.current_pending_balance:,.2f}")

    if not sorted_customers:
        lines.append("No outstanding payments.")

    return "\n".join(lines)

def format_inventory_for_telegram(inventory_items: List[dict]) -> str:
    """Format top 10 inventory/stock items for Telegram."""
    lines = [
        "📦 *Current Stock Levels*",
        "",
    ]
    for item in inventory_items[:10]:
        name = item.get("item_name", "Unknown Item")
        qty = item.get("current_quantity", 0) or item.get("quantity", 0) or 0
        unit = item.get("unit", "")
        lines.append(f"• *{name}*: {qty:,.1f} {unit}")

    if not inventory_items:
        lines.append("No inventory records found.")

    return "\n".join(lines)

def format_production_preview(size_ml: int, machine_name: str, boxes: int) -> str:
    """Format the guided production confirmation preview."""
    return (
        "📝 *Confirm Production Entry*\n\n"
        f"• *Size:* {size_ml} ml\n"
        f"• *Machine:* {machine_name}\n"
        f"• *Boxes:* {boxes}\n\n"
        "Do you want to confirm this entry?"
    )

def format_attendance_preview(worker_name: str, status: str) -> str:
    """Format the guided attendance confirmation preview."""
    return (
        "📝 *Confirm Attendance Entry*\n\n"
        f"• *Worker:* {worker_name}\n"
        f"• *Status:* {status}\n\n"
        "Do you want to confirm this entry?"
    )

def format_action_result(action_type: str, details: str) -> str:
    """Format a standard action success/failure outcome."""
    emoji = "✅" if "Recorded" in details or "Marked" in details or "Success" in details else "❌"
    return f"{emoji} *{action_type}*\n\n{details}"
