import json

from services.briefing_service import render_morning_briefing_message
from services.llm_explain import explain_briefing, to_llm_input


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, _ttl, value):
        self.values[key] = value


def privacy_snapshot():
    return {
        "owner_name": "Prashant Sharma",
        "production": {"produced": 100, "target": 120, "gap": 20},
        "workers": {
            "present": 2,
            "absent": 1,
            "details": [
                {"worker_name": "Ramesh", "status": "Present"},
                {"worker_name": "Suresh", "status": "Absent"},
            ],
        },
        "sales": {
            "invoice_count": 1,
            "amount": 5000,
            "collections_received": 2000,
            "outstanding_amount": 3000,
            "customer_name": "ABC Traders",
        },
        "suppliers": [
            {"supplier_name": "Shivam Paper Mills", "amount": 1500},
            {"supplier_name": "Shivam Paper Mills", "amount": 500},
        ],
        "risk_items": [
            {
                "severity": "warning",
                "type": "outstanding",
                "label": "ABC Traders",
                "pending_amount": 3000,
                "message": "ABC Traders outstanding payment",
            }
        ],
    }


def test_customer_supplier_worker_and_owner_names_are_redacted():
    safe = to_llm_input(privacy_snapshot())
    assert safe["owner_name"] == "Factory Owner"
    assert safe["sales"]["customer_name"] == "Customer 1"
    assert safe["risk_items"][0]["label"] == "Customer 1"
    assert safe["workers"]["details"][0]["worker_name"] == "Worker 1"
    assert safe["workers"]["details"][1]["worker_name"] == "Worker 2"
    assert safe["suppliers"][0]["supplier_name"] == "Supplier 1"
    assert safe["suppliers"][1]["supplier_name"] == "Supplier 1"


def test_llm_input_contains_no_original_names_and_does_not_mutate_snapshot():
    original = privacy_snapshot()
    safe = to_llm_input(original)
    serialized = json.dumps(safe, ensure_ascii=False)
    for name in ("Prashant Sharma", "ABC Traders", "Shivam Paper Mills", "Ramesh", "Suresh"):
        assert name not in serialized
    assert original["sales"]["customer_name"] == "ABC Traders"
    assert original["risk_items"][0]["label"] == "ABC Traders"


def test_provider_receives_only_redacted_input():
    received = {}

    def provider(safe_snapshot):
        received.update(safe_snapshot)
        return {
            "cost_explanation": "",
            "health_explanation": "",
            "wastage_explanation": "",
            "profit_explanation": "",
            "per_size_explanation": "",
            "action_items": [],
            "model_version": "future-model",
            "tokens_used": 0,
        }

    outcome = explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=privacy_snapshot(),
        provider=provider,
        cache=None,
    )
    assert outcome.tier == "ai"
    serialized = json.dumps(received, ensure_ascii=False)
    assert "ABC Traders" not in serialized
    assert "Shivam Paper Mills" not in serialized
    assert "Ramesh" not in serialized
    assert received["owner_name"] == "Factory Owner"


def test_explanation_may_repeat_redacted_alias_without_false_hallucination():
    def provider(_safe_snapshot):
        return {
            "cost_explanation": "",
            "health_explanation": "",
            "wastage_explanation": "",
            "profit_explanation": "Customer 1 has outstanding amount 3000.",
            "per_size_explanation": "",
            "action_items": [],
            "model_version": "future-model",
            "tokens_used": 0,
        }

    outcome = explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=privacy_snapshot(),
        provider=provider,
        cache=MemoryCache(),
    )
    assert outcome.tier == "ai"


def test_deterministic_briefing_still_uses_real_customer_name():
    snapshot = privacy_snapshot()
    message = render_morning_briefing_message(snapshot, "Prashant Sharma", "en")
    assert "Good Morning Prashant Sharma" in message
    assert "Outstanding Alert: ABC Traders" in message


def test_redaction_maps_are_factory_call_isolated():
    factory_a = {"customer_name": "ABC Traders", "worker_name": "Ramesh"}
    factory_b = {"customer_name": "Beta Buyers", "worker_name": "Mohan"}
    safe_a = to_llm_input(factory_a)
    safe_b = to_llm_input(factory_b)
    assert safe_a == {"customer_name": "Customer 1", "worker_name": "Worker 1"}
    assert safe_b == {"customer_name": "Customer 1", "worker_name": "Worker 1"}
    assert "Beta Buyers" not in json.dumps(safe_a)
    assert "ABC Traders" not in json.dumps(safe_b)
