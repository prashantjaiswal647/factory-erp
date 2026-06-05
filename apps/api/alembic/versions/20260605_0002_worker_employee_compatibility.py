"""add Worker compatibility references to legacy employee records

Revision ID: 20260605_0002
Revises: 20260603_0001
Create Date: 2026-06-05
"""

from __future__ import annotations

from alembic import op


revision = "20260605_0002"
down_revision = "20260603_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add and backfill canonical Worker references without removing Employee."""
    op.execute("ALTER TABLE attendance_logs ADD COLUMN IF NOT EXISTS worker_id INTEGER")
    op.execute("ALTER TABLE advance_payments ADD COLUMN IF NOT EXISTS worker_id INTEGER")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_attendance_logs_worker_id_workers'
            ) THEN
                ALTER TABLE attendance_logs
                ADD CONSTRAINT fk_attendance_logs_worker_id_workers
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_advance_payments_worker_id_workers'
            ) THEN
                ALTER TABLE advance_payments
                ADD CONSTRAINT fk_advance_payments_worker_id_workers
                FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_attendance_logs_worker_id ON attendance_logs (worker_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_advance_payments_worker_id ON advance_payments (worker_id)")
    op.execute(
        """
        UPDATE attendance_logs AS attendance
        SET worker_id = worker.id
        FROM employees AS employee
        JOIN workers AS worker
          ON worker.factory_id = employee.factory_id
         AND worker.name = employee.name
        WHERE attendance.employee_id = employee.id
          AND attendance.factory_id = employee.factory_id
          AND attendance.worker_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE advance_payments AS advance
        SET worker_id = worker.id
        FROM employees AS employee
        JOIN workers AS worker
          ON worker.factory_id = employee.factory_id
         AND worker.name = employee.name
        WHERE advance.employee_id = employee.id
          AND advance.factory_id = employee.factory_id
          AND advance.worker_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_logs_factory_date_worker
        ON attendance_logs (factory_id, date, worker_id)
        WHERE worker_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Compatibility columns are intentionally retained to avoid data loss."""
    return None
