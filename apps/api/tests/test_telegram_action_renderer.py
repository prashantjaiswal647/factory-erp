"""
Tests for telegram_action_renderer.py

Verifies:
1. format_outstanding_for_telegram — grand total, top-5 sorting, empty case
2. format_inventory_for_telegram — renders items, top-10 truncation, empty case
3. format_production_preview — correct fields
4. format_attendance_preview — correct fields
5. format_action_result — success and failure emoji logic
"""

import pytest
from decimal import Decimal
from types import SimpleNamespace

from services.telegram_action_renderer import (
    format_outstanding_for_telegram,
    format_inventory_for_telegram,
    format_production_preview,
    format_attendance_preview,
    format_action_result,
)


def make_customer(name: str, balance: Decimal) -> SimpleNamespace:
    return SimpleNamespace(customer_name=name, current_pending_balance=balance)


def make_outstanding(customers, grand_total: Decimal = Decimal("0.00")) -> SimpleNamespace:
    return SimpleNamespace(
        grand_total_outstanding=grand_total,
        customers=customers,
    )


# ---------------------------------------------------------------------------
# Outstanding formatter tests
# ---------------------------------------------------------------------------

def test_outstanding_shows_grand_total():
    customers = [make_customer("Rajan Traders", Decimal("5000.00"))]
    data = make_outstanding(customers, grand_total=Decimal("5000.00"))
    text = format_outstanding_for_telegram(data)
    assert "5,000.00" in text
    assert "Outstanding" in text


def test_outstanding_shows_top_5_only():
    customers = [
        make_customer(f"Customer {i}", Decimal(str(i * 1000)))
        for i in range(8, 0, -1)  # 8 customers
    ]
    data = make_outstanding(customers, grand_total=Decimal("36000.00"))
    text = format_outstanding_for_telegram(data)
    # Only top 5 should appear; customer 8 is highest
    assert "Customer 8" in text
    assert "Customer 4" in text  # 4th highest
    # Customer 3 and below might be excluded after top-5
    # Count occurrences of "Customer" pattern
    import re
    count = len(re.findall(r"\d+\. \*Customer", text))
    assert count == 5, f"Expected 5 customers but found {count}"


def test_outstanding_sorts_descending():
    customers = [
        make_customer("Low Trader", Decimal("100.00")),
        make_customer("High Trader", Decimal("9000.00")),
        make_customer("Mid Trader", Decimal("500.00")),
    ]
    data = make_outstanding(customers, grand_total=Decimal("9600.00"))
    text = format_outstanding_for_telegram(data)
    high_pos = text.index("High Trader")
    low_pos = text.index("Low Trader")
    assert high_pos < low_pos, "Highest balance should appear first"


def test_outstanding_empty_customers():
    data = make_outstanding([], grand_total=Decimal("0.00"))
    text = format_outstanding_for_telegram(data)
    assert "No outstanding" in text


# ---------------------------------------------------------------------------
# Inventory formatter tests
# ---------------------------------------------------------------------------

def test_inventory_renders_items():
    items = [
        {"item_name": "Raw Blank", "current_quantity": 500.0, "unit": "kg"},
        {"item_name": "Poly Bag", "current_quantity": 200.0, "unit": "rolls"},
    ]
    text = format_inventory_for_telegram(items)
    assert "Raw Blank" in text
    assert "500" in text
    assert "Poly Bag" in text


def test_inventory_truncates_at_10():
    items = [
        {"item_name": f"Item {i}", "current_quantity": float(i), "unit": "kg"}
        for i in range(15)
    ]
    text = format_inventory_for_telegram(items)
    # Item 10 through 14 should not appear
    assert "Item 0" in text
    assert "Item 9" in text
    assert "Item 10" not in text


def test_inventory_empty():
    text = format_inventory_for_telegram([])
    assert "No inventory" in text


# ---------------------------------------------------------------------------
# Production preview tests
# ---------------------------------------------------------------------------

def test_production_preview_contains_all_fields():
    text = format_production_preview(150, "Machine A", 200)
    assert "150" in text
    assert "Machine A" in text
    assert "200" in text
    assert "Confirm" in text


# ---------------------------------------------------------------------------
# Attendance preview tests
# ---------------------------------------------------------------------------

def test_attendance_preview_contains_all_fields():
    text = format_attendance_preview("Ramesh Kumar", "Present")
    assert "Ramesh Kumar" in text
    assert "Present" in text
    assert "Confirm" in text


# ---------------------------------------------------------------------------
# format_action_result tests
# ---------------------------------------------------------------------------

def test_format_action_result_success_emoji():
    text = format_action_result("Production", "Recorded successfully")
    assert "✅" in text


def test_format_action_result_failure_emoji():
    text = format_action_result("Error", "Something failed")
    assert "❌" in text


def test_format_action_result_contains_action_and_detail():
    text = format_action_result("Attendance", "Marked Present")
    assert "Attendance" in text
    assert "Marked Present" in text
