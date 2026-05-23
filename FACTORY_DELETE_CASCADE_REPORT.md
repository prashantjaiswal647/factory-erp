# Factory Delete Cascade Report

## Relationship Map

Detailed table-by-table mapping is documented in `FACTORY_DELETE_RELATIONSHIP_MAP.md`.

## Backend Behavior

Single delete:

- Endpoint: `DELETE /api/super-admin/factories/{factory_id}`
- Body: `{ "confirmation": "DELETE FACTORY" }`
- Requires Super Admin auth.
- Requires `ENABLE_SUPER_ADMIN_FACTORY_DELETE=true`.
- Calls the shared `delete_factory_cascade(...)` helper.
- Audit action: `DELETE_FACTORY_CASCADE`.

Bulk delete:

- Endpoint: `DELETE /api/super-admin/factories/bulk-delete`
- Body: `{ "factory_ids": [1, 2], "confirmation": "DELETE SELECTED FACTORIES" }`
- Requires Super Admin auth.
- Requires `ENABLE_SUPER_ADMIN_BULK_DELETE=true`.
- Validates all selected factories before deletion.
- Calls the same `delete_factory_cascade(...)` helper for each selected factory in one transaction.
- Audit action: `BULK_DELETE_FACTORIES_CASCADE`.

Preview:

- Bulk preview: `POST /api/super-admin/factories/bulk-delete-preview`
- Single preview: `GET /api/super-admin/factories/{factory_id}/delete-preview`
- Preview includes owner action, warnings, worker/staff counts, and related business data counts.

## Owner Rule

The current auth model has one `factory_id` per user. If a user belongs to the deleted factory, that user is deleted with the factory. If a factory owner reference points to a user outside the deleted factory, that user is kept.

## Worker / Staff Rule

Workers, employees, attendance, advance payments, hisab settlements, and users linked by `factory_id` are deleted as tenant data. Shared/global/admin accounts are not touched.

## Frontend UI

The Super Admin factories page now supports:

- single `Delete Factory` action per row
- single delete preview modal
- owner action display
- worker/staff count display
- business record counts
- exact confirmation phrase `DELETE FACTORY`
- bulk delete preview with owner action and counts
- final delete buttons disabled when server flags are off

## Env Flags

```env
ENABLE_SUPER_ADMIN_BULK_DELETE=false
ENABLE_SUPER_ADMIN_FACTORY_DELETE=false
SUPER_ADMIN_BULK_DELETE_MAX=50
```

Destructive actions default to disabled and must be enabled intentionally.

## Audit Logging

Single delete writes:

- `DELETE_FACTORY_CASCADE`

Bulk delete writes:

- `BULK_DELETE_FACTORIES_CASCADE`

Audit logs keep old previews, owner action, counts, deleted IDs, and deleted count summaries. New audit records are retained as compliance history.

## Known Limitations

- No factory-linked upload/file metadata table was found in current models, so physical file deletion is not implemented.
- PostgreSQL disk space is reusable after `DELETE`, but OS-level disk space may not shrink until manual maintenance.

## Commands Run

Verified locally:

```bash
cd apps/web
npm run build
```

Result: passed.

```bash
docker compose build api
docker compose run --rm api python -m pytest tests
```

Result: API image build passed. Backend test suite passed: 35 passed.

```bash
cd apps/web
PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:local
```

Result: passed: 30 passed, 2 skipped.

```bash
cd apps/web
PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:ux
```

Result: passed: 14 passed.
