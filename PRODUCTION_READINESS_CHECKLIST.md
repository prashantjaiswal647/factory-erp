# Production Readiness Checklist: Pilot Phase

Auditing all modules and backend logic before deploying to live VPS pilot nodes.

| Module | Verification Goal | Status | Notes |
|---|---|---|---|
| **Security** | Check multi-tenant query isolation and role permission limits. | **READY** | Active user factory scoping verified on all endpoints. |
| **Backups** | DB backup restoration dry run via docker dump script. | **READY** | Passed restore comparison drills successfully. |
| **Alembic** | Revision migrations run check on clean PostgreSQL docker base. | **READY** | Baseline model migration executes without structural errors. |
| **Telegram** | Command center inline callback button flows. | **READY** | Sub-owner masking & Owner menu flows fully tested. |
| **Invoice PDF**| PDF document layout with Tax, GSTIN, and Signatures. | **READY** | Local ReportLab PDF generation executes cleanly. |
| **SMTP** | OTP and credential verification alert emails. | **PARTIAL**| SMS/OTP providers configured for trial, requires production keys. |
| **Collection WR**| War room widgets aging bucket parsing and top due logs. | **READY** | Verified math and query performance under active load. |
| **Recovery** | Reminders and action trigger logs. | **READY** | Inline callback routes successfully generate messages. |
| **Briefings** | Snapshot memory aggregation logs and history API. | **READY** | History detail and masking filters fully operational. |
