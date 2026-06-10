# Current Status: Munshi AI

## Completed Features
- **Multi-Tenant Architecture**: Strict `factory_id` isolation across all business logic.
- **Inventory Management**: Raw materials and finished goods tracking.
- **Production Tracking**: Machine-based output and shift logging.
- **Sales Module**: Customer management and sales entry.
- **Payments**: Cashfree integration for subscription and payment collection.
- **Dashboard**: Role-based views for factory performance.
- **Subscription System**: Trial management and automated billing states.
- **Super Admin**: Control room for factory oversight and system audits.
- **Telegram Integration**: Basic alerts and user binding.

## In Progress
- **Telegram Welcome Assistant**: Automated onboarding flow for new Telegram users.
- **Telegram Inline Buttons**: Enhanced interactive action menus.
- **Role-Based Telegram Channels**: Isolating alerts based on user role (Owner vs Supervisor).

## Known Issues & Blockers
### P0 - Pilot Prerequisites
- **CI Configuration**: Alignment of GitHub CI with `npm run build`.
- **Error Sanitization**: Ensuring generic 500 responses to prevent internal leakage.
- **Secret Management**: Routine rotation of exposed API/Test keys.

### P1 - MVP Fixes
- **Bulk Upload Idempotency**: Eliminating crashes during same-file re-uploads.
- **Validation UI**: Completing the frontend report for Excel import errors.
- **RBAC Drift**: Aligning frontend route guards with backend permissions.
- **UI Hardcoding**: Removing absolute production URLs from the sidebar.
- **Duplicate Models**: Consolidating `Employee`/`Worker` and `Expense` models.

### P2 - Scale/Security
- **JWT Storage**: Migrating from `localStorage` to secure cookies.
- **Subscription Automation**: Full Razorpay/Cashfree webhook lifecycle automation.
- **Monitoring**: Lack of centralized API/DB/n8n health monitoring.
- **Connection Pooling**: pgBouncer needed for 10+ factories.
