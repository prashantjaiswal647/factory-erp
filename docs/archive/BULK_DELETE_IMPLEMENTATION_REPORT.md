# Bulk Delete Implementation Report

## Backend Changes

Added protected Super Admin endpoints:

- `GET /api/super-admin/settings`
- `POST /api/super-admin/factories/bulk-delete-preview`
- `DELETE /api/super-admin/factories/bulk-delete`

Added helper functions in `apps/api/routers/super_admin.py`:

- `validate_bulk_factory_ids`
- `factory_delete_preview`
- `combine_preview_counts`
- `delete_factory_cascade`

The same cascade helper is now used by both single factory delete and bulk factory delete.

Bulk delete is protected by existing Super Admin JWT authorization. Normal factory owners cannot call `/api/super-admin/*`.

## Cascade Delete Coverage

The cascade helper deletes factory-linked records in dependency order, including:

- production: `daily_productions`, `production_logs`
- inventory/raw materials: `factory_inventory`, `inventory`, `raw_materials`, stock tables
- sales/orders/invoices: `daily_sales`, `sales_invoices`, `orders`, `order_items`
- expenses/payments: `factory_expenses`, `expense_logs`, `payments`, `subscription_payments`
- staff/attendance: `users`, `employees`, `workers`, `attendance_logs`, `advance_payments`, `hisab_settlements`
- machines/products/costing: `machines`, `machine_onboardings`, `machine_templates`, packaging/product/costing tables
- usage: `app_usage_logs`, `token_usage_logs`
- signup/admin forms linked by `factory_id`: custom plan enquiries and demo bookings

Admin audit logs are kept as compliance history. Old factory-specific audit logs are counted in preview but are not deleted. The new bulk delete audit log is also kept.

## Owner Handling

The current schema links each user to exactly one `factory_id`, so users belonging to the deleted factory are deleted as related records. There is no multi-factory owner relationship in the current model. The backend clears `factory.owner_id` and `factory.owner_phone_number` before user deletion to avoid foreign-key blocking.

## Safety Environment Variables

Added to `.env.example`:

```env
ENABLE_SUPER_ADMIN_BULK_DELETE=false
ENABLE_SUPER_ADMIN_FACTORY_DELETE=false
SUPER_ADMIN_BULK_DELETE_MAX=50
```

Behavior:

- Preview endpoint works while delete is disabled.
- Bulk delete endpoint returns `403` unless `ENABLE_SUPER_ADMIN_BULK_DELETE=true`.
- Single delete endpoint returns `403` unless `ENABLE_SUPER_ADMIN_FACTORY_DELETE=true`.
- More than `SUPER_ADMIN_BULK_DELETE_MAX` selected factories is rejected.
- Confirmation phrase must be exactly `DELETE SELECTED FACTORIES`.

## Audit Logging

Every successful bulk delete creates:

- `action_type = BULK_DELETE_FACTORIES`
- `entity_type = factory`
- `entity_id = [deleted factory ids]`
- `old_value = selected factories and related record counts`
- `new_value = deleted flag, deleted factory ids, deleted counts`

The delete and audit write happen in one database transaction. If deletion fails, the transaction is rolled back.

Fix note:

- Bulk deletes with many selected factories can make a long audit `entity_id` string. The audit helper now truncates `entity_id` to the database column limit while preserving the full deleted factory ID list in `old_value` and `new_value`.

## Frontend Changes

Updated `/munshi-control-room/factories`:

- row checkbox with `data-testid="factory-row-checkbox"`
- select-all checkbox with `data-testid="factory-select-all"`
- selected count indicator
- bulk action button with `data-testid="bulk-delete-factories-button"`
- preview modal with `data-testid="bulk-delete-preview-modal"`
- confirmation input with `data-testid="bulk-delete-confirmation-input"`
- final delete button with `data-testid="bulk-delete-final-button"`
- error message with `data-testid="bulk-delete-error"`
- success toast with `data-testid="bulk-delete-success-toast"`

The UI calls `/api/super-admin/settings` and blocks final deletion when the backend disables bulk delete. Preview remains available so the Super Admin can inspect affected records before enabling the server flag.

After successful deletion, the UI:

- closes the modal
- clears selected factory IDs
- refetches factories
- shows success toast

## Manual Test Steps

1. Start backend and frontend locally.
2. Set local backend env:

```env
ENABLE_SUPER_ADMIN_BULK_DELETE=true
SUPER_ADMIN_BULK_DELETE_MAX=50
```

3. Login as Super Admin.
4. Open `/munshi-control-room/factories`.
5. Select test factories.
6. Click `Delete Selected Factories`.
7. Review affected records in the preview modal.
8. Type `DELETE SELECTED FACTORIES`.
9. Click `Permanently Delete`.
10. Verify factories disappear from UI.
11. Refresh the page and confirm they do not reappear.
12. Check dashboard counts and audit logs.

## PostgreSQL Maintenance Note

PostgreSQL `DELETE` removes rows and makes the space reusable by PostgreSQL, but operating system disk space may not immediately reduce.

After large cleanup, manual maintenance can use:

```sql
VACUUM ANALYZE;
```

Only if OS disk space must be returned and downtime/table locks are acceptable:

```sql
VACUUM FULL;
```

The app does not expose or run `VACUUM FULL` automatically.

## Tests Added

- Playwright: factories page row checkboxes and preview confirmation UX.
- Playwright: final delete remains disabled when server config disables bulk delete.
- Backend unit tests: empty factory IDs rejected, max factory limit enforced, cascade removes related records.

## Commands Run

- `npm run build` from `apps/web`: passed.
- `PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:local`: 30 passed, 2 skipped. Skips require explicit Super Admin credentials or mutation opt-in.
- `PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:ux`: 14 passed.
- `docker compose build api`: passed.
- `docker compose run --rm api python -m pytest tests`: 35 passed.
