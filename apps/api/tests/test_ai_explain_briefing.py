from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from models import Customer, SalesInvoice, OutstandingBill
from schemas import BriefingExplanation
from services.briefing_service import build_briefing, render_morning_briefing_message
from tests.test_cost_per_cup import make_db
from tests.test_weekly_digest import seed_week


SNAPSHOT = {
    "date": "2026-06-07",
    "production": {"produced": 100, "target": 120, "gap": 20},
    "workers": {"present": 10, "absent": 2},
    "sales": {"invoice_count": 2, "amount": 1000, "collections_received": 500, "outstanding_amount": 500, "customer_name": "ABC Traders"},
    "risk_items": [],
}


def make_valid_payload_for_snapshot(safe_snapshot):
    from services.llm_explain import _source_numbers
    allowed = list(_source_numbers(safe_snapshot))
    num1 = str(allowed[0]) if len(allowed) > 0 else "0"
    num2 = str(allowed[1]) if len(allowed) > 1 else "0"
    return {
        "cost_explanation": f"Cost is {num1}.",
        "health_explanation": f"Health is {num2}.",
        "wastage_explanation": "",
        "profit_explanation": "",
        "per_size_explanation": "",
        "action_items": ["Review collections today."],
        "model_version": "llama-3.3-70b-versatile",
        "tokens_used": 100,
    }


def test_briefing_mocked_llm_success():
    engine, db = make_db()
    try:
        seed_week(db)
        result = build_briefing(
            db,
            factory_id=1,
            briefing_date=date(2026, 6, 7),
            owner_name="Owner 1",
            language="en",
            provider=make_valid_payload_for_snapshot,
        )
        assert result["ai_explanation"] is not None
        assert "Cost is" in result["ai_explanation"]["cost_explanation"]
        assert result["ai_observability"]["cache_hit"] is False
        assert result["ai_observability"]["fallback_reason"] is None
    finally:
        db.close()
        engine.dispose()


def test_briefing_mocked_llm_hallucinated_number_rejected():
    engine, db = make_db()
    try:
        seed_week(db)
        def provider(safe_snapshot):
            payload = make_valid_payload_for_snapshot(safe_snapshot)
            payload["profit_explanation"] = "Profit is 999999." # Hallucinated number not in snapshot
            return payload

        result = build_briefing(
            db,
            factory_id=1,
            briefing_date=date(2026, 6, 7),
            owner_name="Owner 1",
            language="en",
            provider=provider,
        )
        assert result["ai_explanation"] is None
        assert result["ai_observability"]["fallback_reason"] is not None
        assert "unsupported numeric values" in result["ai_observability"]["fallback_reason"]
    finally:
        db.close()
        engine.dispose()


def test_briefing_mocked_llm_pii_leak_rejected():
    engine, db = make_db()
    try:
        seed_week(db)
        # Seed customer and invoice to ensure customer name is in snapshot
        customer = Customer(factory_id=1, name="ABC Traders")
        db.add(customer)
        db.flush()
        db.add(
            SalesInvoice(
                factory_id=1,
                customer_id=customer.id,
                date=date(2026, 6, 7),
                cup_size_ml=250,
                packaging_profile_id=1,
                boxes_sold=1,
                total_amount=Decimal("1000"),
                amount_paid=Decimal("500"),
            )
        )
        db.add(
            OutstandingBill(
                factory_id=1,
                customer_id=customer.id,
                tracking_number="BILL-101",
                bill_date=date(2026, 6, 7),
                bill_amount=Decimal("150000"),
                amount_paid=Decimal("0"),
                balance_amount=Decimal("150000"),
                status="active",
            )
        )
        db.commit()

        def provider(safe_snapshot):
            payload = make_valid_payload_for_snapshot(safe_snapshot)
            payload["profit_explanation"] = "ABC Traders is leaked here." # Original customer name leaked
            return payload

        result = build_briefing(
            db,
            factory_id=1,
            briefing_date=date(2026, 6, 7),
            owner_name="Owner 1",
            language="en",
            provider=provider,
        )
        assert result["ai_explanation"] is None
        assert result["ai_observability"]["fallback_reason"] is not None
        assert "leaked PII" in result["ai_observability"]["fallback_reason"]
    finally:
        db.close()
        engine.dispose()


def test_briefing_cache_hit_used():
    engine, db = make_db()
    try:
        seed_week(db)
        # First call creates cache
        build_briefing(
            db,
            factory_id=1,
            briefing_date=date(2026, 6, 7),
            owner_name="Owner 1",
            language="en",
            provider=make_valid_payload_for_snapshot,
        )
        db.commit()

        # Second call uses cache (with provider=None)
        result = build_briefing(
            db,
            factory_id=1,
            briefing_date=date(2026, 6, 7),
            owner_name="Owner 1",
            language="en",
            provider=None,
        )
        assert result["ai_explanation"] is not None
        assert result["ai_observability"]["cache_hit"] is True
    finally:
        db.close()
        engine.dispose()


def test_briefing_llm_failure_falls_back_deterministic():
    engine, db = make_db()
    try:
        seed_week(db)
        def failing_provider(_safe):
            raise TimeoutError("provider offline")
        
        result = build_briefing(
            db,
            factory_id=1,
            briefing_date=date(2026, 6, 7),
            owner_name="Owner 1",
            language="en",
            provider=failing_provider,
        )
        assert result["ai_explanation"] is None
        assert result["ai_observability"]["fallback_reason"] == "provider timeout"
    finally:
        db.close()
        engine.dispose()


def test_telegram_summary_includes_insight_only_when_safe():
    snapshot = {**SNAPSHOT}
    explanation = BriefingExplanation.model_validate(make_valid_payload_for_snapshot(snapshot))
    
    # Safe path
    message_safe = render_morning_briefing_message(
        snapshot,
        "Owner 1",
        "en",
        summary_mode=True,
        explanation=explanation,
    )
    assert "✨ Munshi Insight" in message_safe
    assert "✅ Action Items" in message_safe

    # Unsafe path (no explanation)
    message_unsafe = render_morning_briefing_message(
        snapshot,
        "Owner 1",
        "en",
        summary_mode=True,
        explanation=None,
    )
    assert "✨ Munshi Insight" not in message_unsafe


def test_hindi_hinglish_output_works_with_mocked_responses():
    snapshot = {**SNAPSHOT}
    explanation = BriefingExplanation.model_validate(make_valid_payload_for_snapshot(snapshot))
    
    hindi_msg = render_morning_briefing_message(
        snapshot,
        "Owner 1",
        "hi",
        summary_mode=True,
        explanation=explanation,
    )
    assert "✨ Munshi Insight" in hindi_msg

    hinglish_msg = render_morning_briefing_message(
        snapshot,
        "Owner 1",
        "hinglish",
        summary_mode=True,
        explanation=explanation,
    )
    assert "✨ Munshi Insight" in hinglish_msg
