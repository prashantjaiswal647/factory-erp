from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import DailyFactoryHealthSnapshot, Factory
from routers.factory_health import admin_history, history
from services.factory_health import factory_health_history
from tests.test_cost_per_cup import make_db


TODAY = date.today()


def add_snapshot(db, factory_id: int, day: date, score: str, risk: str = "Collections"):
    if db.get(Factory, factory_id) is None:
        db.add(Factory(id=factory_id, name=f"History Factory {factory_id}", subscription_status="active"))
        db.flush()
    numeric = Decimal(score)
    db.add(
        DailyFactoryHealthSnapshot(
            factory_id=factory_id,
            snapshot_date=day,
            production_score=numeric,
            attendance_score=numeric,
            collections_score=numeric,
            inventory_score=numeric,
            cost_score=numeric,
            overall_score=numeric,
            health_status="GOOD" if numeric >= 70 else "WARNING",
            largest_strength="Production",
            largest_risk=risk,
        )
    )
    db.commit()


def test_history_endpoint_returns_ascending_dates_and_own_factory_only():
    engine, db = make_db()
    try:
        add_snapshot(db, 1, TODAY - timedelta(days=2), "70")
        add_snapshot(db, 1, TODAY, "80")
        add_snapshot(db, 2, TODAY - timedelta(days=1), "99")
        result = history(days=30, current_user=SimpleNamespace(factory_id=1), db=db)
        assert [item["date"] for item in result["items"]] == [
            (TODAY - timedelta(days=2)).isoformat(),
            TODAY.isoformat(),
        ]
        assert all(item["overall_score"] != 99 for item in result["items"])
    finally:
        db.close()
        engine.dispose()


def test_super_admin_selected_factory_history():
    engine, db = make_db()
    try:
        add_snapshot(db, 1, TODAY, "60")
        add_snapshot(db, 2, TODAY, "90")
        result = admin_history(factory_id=2, response=SimpleNamespace(headers={}), days=30, db=db)
        assert len(result["items"]) == 1
        assert result["items"][0]["overall_score"] == 90
    finally:
        db.close()
        engine.dispose()


def test_trend_direction_boundaries():
    engine, db = make_db()
    try:
        for offset, value in enumerate([60, 60, 60, 60, 60, 60, 90]):
            add_snapshot(db, 1, TODAY - timedelta(days=6 - offset), str(value))
        result = factory_health_history(db, 1, 30, end_date=TODAY)
        assert result["summary"]["trend_direction"] == "IMPROVING"

        db.query(DailyFactoryHealthSnapshot).filter_by(factory_id=1, snapshot_date=TODAY).update(
            {DailyFactoryHealthSnapshot.overall_score: Decimal("30")}
        )
        db.commit()
        result = factory_health_history(db, 1, 30, end_date=TODAY)
        assert result["summary"]["trend_direction"] == "DECLINING"
    finally:
        db.close()
        engine.dispose()


def test_best_and_worst_day_are_deterministic():
    engine, db = make_db()
    try:
        add_snapshot(db, 1, TODAY - timedelta(days=2), "80")
        add_snapshot(db, 1, TODAY - timedelta(days=1), "50")
        add_snapshot(db, 1, TODAY, "90")
        result = factory_health_history(db, 1, 30, end_date=TODAY)
        assert result["summary"]["best_day"]["date"] == TODAY.isoformat()
        assert result["summary"]["worst_day"]["date"] == (TODAY - timedelta(days=1)).isoformat()
    finally:
        db.close()
        engine.dispose()


def test_missing_history_is_graceful():
    engine, db = make_db()
    try:
        result = factory_health_history(db, 1, 30, end_date=TODAY)
        assert result["items"] == []
        assert result["summary"]["current_score"] is None
        assert result["summary"]["trend_direction"] == "STABLE"
    finally:
        db.close()
        engine.dispose()


def test_health_history_routes_are_registered():
    from main import app

    paths = {route.path for route in app.routes}
    assert "/api/factory-health/history" in paths
    assert "/api/admin/factory-health/{factory_id}/history" in paths


def test_risk_route_mapping_targets_existing_routes():
    test_file = Path(__file__).resolve()
    repo_root = next(
        (
            parent
            for parent in test_file.parents
            if (parent / "apps/web/src/App.tsx").is_file()
        ),
        None,
    )
    if repo_root is None:
        pytest.skip("Frontend source is not included in the API-only image")
    mapping = (repo_root / "apps/web/src/lib/factoryHealthRoutes.ts").read_text(encoding="utf-8")
    app_routes = (repo_root / "apps/web/src/App.tsx").read_text(encoding="utf-8")
    expected = {
        "Production": "/production",
        "Attendance": "/attendance",
        "Collections": "/outstanding",
        "Inventory": "/inventory",
        "Cost": "/cost-intelligence",
    }
    for risk, route in expected.items():
        assert f'{risk}: "{route}"' in mapping
        assert f'path="{route.lstrip("/")}"' in app_routes
