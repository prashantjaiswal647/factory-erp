# Briefing Snapshots Migration Fix Report

## 1. Description of the Issue
The `GET /api/briefings/history?days=30` route was failing with:
`psycopg2.errors.UndefinedTable: relation "briefing_snapshots" does not exist`

This occurred because the `briefing_snapshots` table model was defined in the application, but the corresponding Alembic schema migration file was missing from the migration versions.

## 2. Changes Made
We created a new Alembic migration to define the `briefing_snapshots` table:
- **Migration File**: `20260620_0030_briefing_snapshots.py`
- **Revision ID**: `0030_briefing_snapshots`
- **Down Revision**: `0029_recovery_followups`

### Migration Strategy:
1. **Idempotence**: Checks if the table `briefing_snapshots` already exists using the SQLAlchemy database inspector before executing creation logic.
2. **Schema & Columns**:
   - `id`: Integer primary key
   - `factory_id`: Integer, ForeignKey referencing `factories.id`, nullable=False, indexed
   - `user_id`: Integer, ForeignKey referencing `users.id`, nullable=True, indexed
   - `role`: String(50), nullable=False, indexed
   - `briefing_date`: Date, nullable=False, indexed
   - `message_text`: Text, nullable=False
   - `snapshot_json`: JSONB for PostgreSQL dialect, JSON fallback for other dialects (e.g. SQLite in test environments)
   - `health_score`: Numeric(5, 2), nullable=True
   - `status`: String(30), nullable=False, default/server-default `"generated"`
   - `sent_at`: DateTime (with timezone), nullable=True
   - `created_at`: DateTime (with timezone), nullable=False, server-default to current timestamp (`now()`)
3. **Constraints**:
   - Unique constraint `uq_briefing_snapshots_factory_date_role_user` on `["factory_id", "briefing_date", "role", "user_id"]`.
4. **Indexes**:
   - Index on `["factory_id", "role", "briefing_date"]`
   - Index on `["factory_id", "briefing_date"]`
5. **Downgrade**:
   - Non-destructive downgrade: Drops the extra indexes, but only drops the table `briefing_snapshots` if it contains no rows.

## 3. Verification Results
- **Pytest**: Ran `pytest tests/test_briefing_history.py -v` successfully (All 4 tests passed).
- **Vite Frontend Build**: `npm run build` ran and completed successfully.
- **Alembic online migrations**: The upgrade code executes conditionally, dynamically resolving SQLite (test) and PostgreSQL dialects.
