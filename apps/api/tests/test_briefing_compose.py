from pathlib import Path

import pytest
import yaml


def _find_repository_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "docker-compose.yml").exists():
            return parent
    return None


def test_scheduler_service_has_restart_policy_and_required_runtime_configuration():
    root = _find_repository_root()
    if root is None:
        pytest.skip("Repository-root docker-compose.yml is not copied into the isolated API image")

    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    scheduler = compose["services"]["briefing-scheduler"]

    assert scheduler["container_name"] == "ai-erp-briefing-scheduler"
    assert scheduler["restart"] in {"always", "unless-stopped"}
    assert scheduler["command"] == "python -m services.briefing_scheduler"
    assert scheduler["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert scheduler["environment"] == [
        "PYTHONDONTWRITEBYTECODE=1",
        "DATABASE_URL=${DATABASE_URL:-postgresql://postgres:postgres@postgres:5432/ai_erp_db}",
        "MORNING_BRIEFING_MAX_RETRIES=${MORNING_BRIEFING_MAX_RETRIES:-3}",
        "TZ=Asia/Kolkata",
    ]


def test_cost_scheduler_service_has_nightly_runtime_configuration():
    root = _find_repository_root()
    if root is None:
        pytest.skip("Repository-root docker-compose.yml is not copied into the isolated API image")

    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    scheduler = compose["services"]["cost-scheduler"]

    assert scheduler["container_name"] == "ai-erp-cost-scheduler"
    assert scheduler["restart"] in {"always", "unless-stopped"}
    assert scheduler["command"] == "python -m services.cost_scheduler"
    assert scheduler["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert "TZ=Asia/Kolkata" in scheduler["environment"]


def test_factory_health_scheduler_runs_after_cost_scheduler():
    root = _find_repository_root()
    if root is None:
        pytest.skip("Repository-root docker-compose.yml is not copied into the isolated API image")

    compose = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    scheduler = compose["services"]["factory-health-scheduler"]

    assert scheduler["container_name"] == "ai-erp-factory-health-scheduler"
    assert scheduler["restart"] in {"always", "unless-stopped"}
    assert scheduler["command"] == "python -m services.factory_health_scheduler"
    assert scheduler["depends_on"]["cost-scheduler"]["condition"] == "service_started"
    assert "TZ=Asia/Kolkata" in scheduler["environment"]
