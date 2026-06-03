# Disaster Recovery Restore Drill Report

Date: 2026-06-04 IST

Environment: Contabo production deployment for `https://munshiai.co.in`

## Summary

The Contabo production PostgreSQL backup was restored into a disposable restore target and validated with table-count comparisons. The live production database was not dropped, overwritten, or restored into.

- Backup file: `storage/backups/dr_contabo_restore_drill_20260603_205906.dump`
- Production container: `ai-erp-postgres`
- Restore target: disposable database `dr_restore_check`
- Restore method: `pg_dump -Fc` backup restored with `pg_restore` into disposable DB
- Verdict: READY for pilot restore-readiness requirements

## Commands

Backup command:

```bash
docker exec ai-erp-postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > storage/backups/dr_contabo_restore_drill_20260603_205906.dump
```

Restore command:

```bash
pg_restore --no-owner -d dr_restore_check storage/backups/dr_contabo_restore_drill_20260603_205906.dump
```

## Table Count Comparison

| Table | Production count | Restored count | Status |
|---|---:|---:|---|
| `factories` | 3 | 3 | OK |
| `users` | 5 | 5 | OK |
| `workers` | 8 | 8 | OK |
| `machines` | 14 | 14 | OK |
| `customers` | 0 | 0 | OK |
| `inventory` | 28 | 28 | OK |
| `factory_inventory` | 0 | 0 | OK |
| `blank_stock` | 17 | 17 | OK |
| `bottom_stock` | 5 | 5 | OK |
| `box_stock` | 2 | 2 | OK |
| `plastic_stock` | 8 | 8 | OK |
| `polybag_stock` | 0 | 0 | OK |
| `final_product_stock` | 0 | 0 | OK |
| `finished_goods_stock` | 20 | 20 | OK |
| `daily_productions` | 0 | 0 | OK |
| `production_logs` | 0 | 0 | OK |
| `sales_invoices` | 0 | 0 | OK |
| `invoice_documents` | 0 | 0 | OK |
| `outstanding_bills` | 0 | 0 | OK |
| `payment_collections` | 0 | 0 | OK |
| `payments` | 0 | 0 | OK |

Mismatches: 0

Missing tables: none in the checked table set.

## Restore Validation

- Restored DB connectivity: `select 1` returned `1`
- Restored DB Alembic revision: `20260603_0001`
- Disposable restore target was removed after validation

## RTO/RPO Estimate

- Backup creation time: 1 second
- Restore time: 5 seconds
- Validation time: 9 seconds
- Estimated technical RTO: 14 seconds for restore plus validation
- End-to-end drill time including backup: 15 seconds
- Estimated RPO: less than 1 minute, because the drill used a fresh backup created immediately before restore validation

## Verdict

DR readiness verdict: READY.

The custom-format production backup was restorable into a disposable database, all checked table counts matched, no checked tables were missing, and the restored database was queryable with the expected Alembic baseline revision.
