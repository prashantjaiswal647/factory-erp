from schemas import BriefingExplanation
from services.llm_explain import explain_briefing, validate_explanation_numbers


SNAPSHOT = {
    "date": "2026-06-07",
    "cost": {"cost_per_cup": 0.58, "seven_day_average": 0.53},
    "factory_health": {"overall_score": 82, "largest_risk": "Collections"},
    "wastage": {"wastage_percentage": 6.2},
    "profit": {"gross_profit": 10500, "profit_margin_percent": 21.8},
    "per_size_profit": {
        "best_size": {"size_ml": 250, "margin_percent": 32},
        "worst_size": {"size_ml": 100, "margin_percent": 4},
    },
}


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, _ttl, value):
        self.values[key] = value


def valid_payload():
    return {
        "cost_explanation": "Cost per cup is 0.58 versus 0.53.",
        "health_explanation": "Factory health score is 82.",
        "wastage_explanation": "Wastage is 6.2%.",
        "profit_explanation": "Profit is 10,500 with margin 21.8%.",
        "per_size_explanation": "250 ml leads at 32%; 100 ml is at 4%.",
        "action_items": ["Review Collections."],
        "model_version": "future-model-v1",
        "tokens_used": 999,
    }


def test_hallucinated_numbers_are_rejected():
    payload = valid_payload()
    payload["profit_explanation"] = "Profit should reach 12,345."
    outcome = explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=SNAPSHOT,
        provider=lambda _snapshot: payload,
        cache=MemoryCache(),
    )
    assert outcome.tier == "deterministic"
    assert outcome.explanation is None
    assert "12345" in outcome.rejected_reason


def test_valid_explanation_is_accepted_and_metadata_numbers_are_excluded():
    explanation = BriefingExplanation.model_validate(valid_payload())
    valid, rejected = validate_explanation_numbers(explanation, SNAPSHOT)
    assert valid is True
    assert rejected == []

    outcome = explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=SNAPSHOT,
        provider=lambda _snapshot: explanation,
        cache=MemoryCache(),
    )
    assert outcome.tier == "ai"
    assert outcome.explanation == explanation


def test_timeout_falls_back_to_deterministic_without_raising():
    def timeout(_snapshot):
        raise TimeoutError("provider unavailable")

    outcome = explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=SNAPSHOT,
        provider=timeout,
        cache=MemoryCache(),
    )
    assert outcome.tier == "deterministic"
    assert outcome.explanation is None
    assert outcome.rejected_reason == "provider timeout"


def test_timeout_uses_snapshot_scoped_cached_response():
    cache = MemoryCache()
    first = explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=SNAPSHOT,
        provider=lambda _snapshot: valid_payload(),
        cache=cache,
    )
    assert first.tier == "ai"

    def timeout(_snapshot):
        raise TimeoutError("provider unavailable")

    second = explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=SNAPSHOT,
        provider=timeout,
        cache=cache,
    )
    assert second.tier == "cache"
    assert second.explanation == first.explanation
    assert second.rejected_reason == "provider timeout"


def test_cache_from_another_snapshot_is_not_reused():
    cache = MemoryCache()
    explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=SNAPSHOT,
        provider=lambda _snapshot: valid_payload(),
        cache=cache,
    )
    changed = {**SNAPSHOT, "factory_health": {"overall_score": 70, "largest_risk": "Collections"}}
    outcome = explain_briefing(
        factory_id=1,
        briefing_date="2026-06-07",
        snapshot=changed,
        provider=None,
        cache=cache,
    )
    assert outcome.tier == "deterministic"
    assert outcome.explanation is None
