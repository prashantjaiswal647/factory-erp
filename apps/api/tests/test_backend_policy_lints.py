import sys
from pathlib import Path

import pytest

TEST_FILE = Path(__file__).resolve()
REPOSITORY_ROOT = next(
    (
        parent
        for parent in TEST_FILE.parents
        if (parent / "scripts" / "check_backend_policies.py").is_file()
    ),
    None,
)
if REPOSITORY_ROOT is None:
    pytest.skip(
        "Repository-level policy script is not included in the API-only image",
        allow_module_level=True,
    )
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.check_backend_policies import run_checks


def write_router(root: Path, source: str, name: str = "sample.py") -> None:
    router_dir = root / "apps" / "api" / "routers"
    router_dir.mkdir(parents=True, exist_ok=True)
    (router_dir / name).write_text(source, encoding="utf-8")


def test_t0_2_bulk_write_without_authenticated_factory_fails(tmp_path):
    write_router(
        tmp_path,
        """
@router.post("/bulk-upload")
def bulk_upload(payload, current_user, db):
    db.add(Item(name=payload.name))
""",
    )

    violations = run_checks(tmp_path)

    assert [violation.rule for violation in violations] == ["T0.2"]


def test_t0_2_bulk_write_with_authenticated_factory_passes(tmp_path):
    write_router(
        tmp_path,
        """
@router.post("/bulk-upload")
def bulk_upload(payload, current_user, db):
    factory_id = current_user.factory_id
    db.add(Item(factory_id=factory_id, name=payload.name))
""",
    )

    assert run_checks(tmp_path) == []


@pytest.mark.parametrize(
    "tenant_field",
    ["factory_id", "tenant_id", "factoryId", "factory_id_str", "factory_id_int"],
)
def test_t0_3_request_supplied_tenant_alias_without_trust_boundary_fails(
    tmp_path,
    tenant_field,
):
    write_router(
        tmp_path,
        f"""
@router.post("/items")
def create_item(payload, db):
    db.add(Item(factory_id=payload.{tenant_field}))
""",
    )

    violations = run_checks(tmp_path)

    assert [violation.rule for violation in violations] == ["T0.3"]
    assert tenant_field in violations[0].message


def test_t0_3_authenticated_and_n8n_routes_are_explicitly_allowed(tmp_path):
    write_router(
        tmp_path,
        """
@router.post("/items")
def create_item(payload, current_user, db):
    if payload.factory_id != current_user.factory_id:
        pass
    db.add(Item(factory_id=current_user.factory_id))

@router.post("/internal/items")
def create_internal_item(payload, _=Depends(require_n8n_api_key), db=None):
    db.add(Item(factory_id=payload.factory_id))
""",
    )

    assert run_checks(tmp_path) == []


def test_t0_4_runtime_create_all_fails_but_tests_and_migrations_are_allowed(tmp_path):
    api_root = tmp_path / "apps" / "api"
    api_root.mkdir(parents=True)
    (api_root / "main.py").write_text("Base.metadata.create_all(bind=engine)\n", encoding="utf-8")
    test_dir = api_root / "tests"
    test_dir.mkdir()
    (test_dir / "test_setup.py").write_text("Base.metadata.create_all(bind=engine)\n", encoding="utf-8")
    migration_dir = api_root / "alembic" / "versions"
    migration_dir.mkdir(parents=True)
    (migration_dir / "revision.py").write_text("Base.metadata.create_all(bind=bind)\n", encoding="utf-8")

    violations = run_checks(tmp_path)

    assert [violation.rule for violation in violations] == ["T0.4"]
