from datetime import date

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base, get_db
from models import ExplanationCache, Factory
from routers.explanation_admin import router
from routers.super_admin import require_super_admin
from services.llm_explain import explain_briefing, generate_snapshot_hash


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _compatibility_patch():
    import inspect

    if "app" in inspect.signature(httpx.Client.__init__).parameters:
        return
    original = httpx.Client.__init__
    if getattr(original, "_explanation_cache_compatible", False):
        return

    def patched(self, *args, app=None, **kwargs):
        return original(self, *args, **kwargs)

    patched._explanation_cache_compatible = True
    httpx.Client.__init__ = patched


def _app(authenticated: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    if authenticated:
        app.dependency_overrides[require_super_admin] = lambda: "admin@munshiai.co.in"
    return app


def _snapshot():
    return {
        "factory_health": {"overall_score": 82, "largest_risk": "Collections"},
        "profit": {"gross_profit": 10500, "profit_margin_percent": 21.8},
        "cost": {"cost_per_cup": 0.58},
        "wastage": {"wastage_percentage": 6.2},
        "per_size_profit": {"best_size": {"size_ml": 250}, "worst_size": {"size_ml": 100}},
        "ignored_runtime_field": "does not affect hash",
    }


def _payload():
    return {
        "cost_explanation": "Cost per cup is 0.58.",
        "health_explanation": "Health score is 82.",
        "wastage_explanation": "Wastage is 6.2%.",
        "profit_explanation": "Profit is 10500 with margin 21.8%.",
        "per_size_explanation": "Best size is 250 and worst size is 100.",
        "action_items": ["Review Collections."],
        "model_version": "future-model-v1",
        "tokens_used": 123,
    }


def setup_function():
    _compatibility_patch()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add_all(
        [
            Factory(id=1, name="Cache Factory A", subscription_status="active"),
            Factory(id=2, name="Cache Factory B", subscription_status="active"),
        ]
    )
    db.commit()
    db.close()


def test_same_snapshot_produces_same_component_hash():
    first = _snapshot()
    second = _snapshot()
    second["ignored_runtime_field"] = "changed"
    assert generate_snapshot_hash(first) == generate_snapshot_hash(second)
    second["profit"]["gross_profit"] = 9000
    assert generate_snapshot_hash(first) != generate_snapshot_hash(second)


def test_cache_miss_generates_and_stores_explanation():
    db = SessionLocal()
    calls = []
    try:
        outcome = explain_briefing(
            factory_id=1,
            briefing_date="2026-06-07",
            language="en",
            snapshot=_snapshot(),
            provider=lambda safe: calls.append(safe) or _payload(),
            cache=None,
            db=db,
        )
        db.commit()
        row = db.query(ExplanationCache).one()
        assert outcome.tier == "ai"
        assert len(calls) == 1
        assert row.model_name == "future-model-v1"
        assert row.token_usage == 123
        assert row.explanation_json == _payload()
        assert row.hit_count == 0
    finally:
        db.close()


def test_cache_hit_skips_provider_and_increments_metric():
    db = SessionLocal()
    calls = []
    try:
        explain_briefing(
            factory_id=1,
            briefing_date="2026-06-07",
            language="en",
            snapshot=_snapshot(),
            provider=lambda _safe: _payload(),
            cache=None,
            db=db,
        )
        db.commit()
        outcome = explain_briefing(
            factory_id=1,
            briefing_date="2026-06-07",
            language="en",
            snapshot=_snapshot(),
            provider=lambda safe: calls.append(safe) or _payload(),
            cache=None,
            db=db,
        )
        db.commit()
        assert outcome.tier == "cache"
        assert calls == []
        assert db.query(ExplanationCache).one().hit_count == 1
    finally:
        db.close()


def test_factory_isolation_keeps_identical_hashes_separate():
    db = SessionLocal()
    try:
        for factory_id in (1, 2):
            explain_briefing(
                factory_id=factory_id,
                briefing_date="2026-06-07",
                snapshot=_snapshot(),
                provider=lambda _safe: _payload(),
                cache=None,
                db=db,
            )
        db.commit()
        rows = db.query(ExplanationCache).order_by(ExplanationCache.factory_id).all()
        assert [row.factory_id for row in rows] == [1, 2]
        assert rows[0].snapshot_hash == rows[1].snapshot_hash
        assert rows[0].id != rows[1].id
    finally:
        db.close()


def test_admin_replay_is_exact_and_stats_are_auditable():
    db = SessionLocal()
    try:
        explain_briefing(
            factory_id=1,
            briefing_date="2026-06-07",
            language="en",
            snapshot=_snapshot(),
            provider=lambda _safe: _payload(),
            cache=None,
            db=db,
        )
        db.commit()
        explain_briefing(
            factory_id=1,
            briefing_date="2026-06-07",
            language="en",
            snapshot=_snapshot(),
            provider=None,
            cache=None,
            db=db,
        )
        db.commit()
        row_id = db.query(ExplanationCache.id).scalar()
    finally:
        db.close()

    client = TestClient(_app(authenticated=True))
    replay = client.get(f"/api/admin/explanations/{row_id}")
    assert replay.status_code == 200
    assert replay.json()["explanation"] == _payload()
    assert replay.json()["model_name"] == "future-model-v1"
    assert replay.json()["token_usage"] == 123
    stats = client.get("/api/admin/explanation-cache/stats")
    assert stats.status_code == 200
    assert stats.json() == {
        "cache_hits": 1,
        "cache_misses": 1,
        "hit_rate": 50.0,
        "stored_explanations": 1,
    }


def test_admin_routes_reject_unauthorized_access():
    client = TestClient(_app(authenticated=False))
    assert client.get("/api/admin/explanations/1").status_code == 401
    assert client.get("/api/admin/explanation-cache/stats").status_code == 401
