# Munshi AI Sprint P4.6 - Invoice Intelligence Report

## Delivered

- Automatic server-side PDF generation using authenticated, factory-scoped invoice data.
- Production-safe invoice allocation using locked factory/settings counters.
- Factory-level duplicate protection through the existing unique invoice constraint.
- Idempotent invoice generation from an existing sale.
- GSTIN format validation and supported GST-rate validation before invoice writes.
- Intra-state CGST/SGST and inter-state IGST calculation.
- Owner branding from factory name, address, GSTIN, invoice prefix, and digital signature settings.
- Download and reprint history through `invoice_delivery_logs`.
- PDF delivery to connected Owner or customer Telegram accounts.
- PDF delivery by SMTP email with validated recipient addresses.
- One-click View, Download, Reprint, Telegram, and Email actions in the invoice ledger.

## Files Changed

- `apps/api/models.py`
- `apps/api/alembic/versions/20260617_0027_invoice_delivery_history.py`
- `apps/api/routers/sales.py`
- `apps/api/tests/test_invoice_intelligence.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/pages/InvoicesPage.tsx`
- `AGENTS.md`

## Safety Controls

- All invoice reads, PDF generation, delivery, reprint, and history queries are factory scoped.
- Delivery failures are recorded without modifying billing, payment, inventory, or invoice totals.
- Telegram bindings are read only and are not reassigned.
- Email addresses are masked in delivery history.
- No E-way bill, complex accounting, or predictive feature was added.

## Verification

- Invoice sequencing, GST validation, reprint history, tenant isolation, PDF smoke, and idempotency tests: passed.
- Frontend production build: passed.
- Frontend Vitest suite: 11 passed.
- Alembic head: `0027_invoice_delivery_history`.

## Deployment

1. Run the validation gate and create the mandatory pre-migration database backup.
2. Apply Alembic revision `0027_invoice_delivery_history`.
3. Configure SMTP variables for email delivery.
4. Rebuild API and web containers, then recreate Caddy.
5. Verify invoice creation, PDF download, Telegram send, email send, and delivery history for one pilot factory.
