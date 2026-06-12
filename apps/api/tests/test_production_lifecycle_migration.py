import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260626_0036_production_lifecycle.py"
)


class FakeInspector:
    def __init__(self, columns=None, indexes=None, foreign_keys=None, checks=None):
        self.columns = set(columns or [])
        self.indexes = set(indexes or [])
        self.foreign_keys = set(foreign_keys or [])
        self.checks = set(checks or [])

    def get_columns(self, _table):
        return [{"name": name} for name in self.columns]

    def get_indexes(self, _table):
        return [{"name": name} for name in self.indexes]

    def get_foreign_keys(self, _table):
        return [{"name": name} for name in self.foreign_keys]

    def get_check_constraints(self, _table):
        return [{"name": name} for name in self.checks]


class FakeOp:
    def __init__(self, inspector):
        self.inspector = inspector

    def get_bind(self):
        return object()

    def add_column(self, _table, column):
        if column.name in self.inspector.columns:
            raise AssertionError(f"duplicate column attempted: {column.name}")
        self.inspector.columns.add(column.name)

    def create_index(self, name, _table, _columns):
        if name in self.inspector.indexes:
            raise AssertionError(f"duplicate index attempted: {name}")
        self.inspector.indexes.add(name)

    def create_foreign_key(self, name, _source, _target, _local, _remote):
        if name in self.inspector.foreign_keys:
            raise AssertionError(f"duplicate foreign key attempted: {name}")
        self.inspector.foreign_keys.add(name)

    def create_check_constraint(self, name, _table, _condition):
        if name in self.inspector.checks:
            raise AssertionError(f"duplicate check attempted: {name}")
        self.inspector.checks.add(name)


def load_migration():
    spec = importlib.util.spec_from_file_location("production_lifecycle_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("existing_columns", [set(), {"shift"}])
def test_upgrade_handles_fresh_and_existing_shift(monkeypatch, existing_columns):
    migration = load_migration()
    inspector = FakeInspector(columns=existing_columns)
    monkeypatch.setattr(migration, "inspect", lambda _bind: inspector)
    monkeypatch.setattr(migration, "op", FakeOp(inspector))

    migration.upgrade()
    migration.upgrade()

    assert {
        "shift",
        "status",
        "created_by_user_id",
        "rejected_by_user_id",
        "rejected_at",
        "rejection_reason",
        "updated_at",
    }.issubset(inspector.columns)
    assert len(inspector.indexes) == 3
    assert len(inspector.foreign_keys) == 2
    assert inspector.checks == {"ck_daily_productions_status"}
