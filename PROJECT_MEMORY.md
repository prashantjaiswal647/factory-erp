# Project Memory: Munshi AI

## Product Overview
Munshi AI is a multi-tenant ERP SaaS designed for small-to-medium manufacturing factories, specifically targeting the paper cup and glass industry. It aims to transition factory owners from manual tracking to AI-powered production and cost intelligence.

## Tech Stack
- **Frontend**: React + Vite, Tailwind CSS, TypeScript.
- **Backend**: FastAPI (Python), SQLAlchemy ORM.
- **Database**: PostgreSQL 16 (Primary), Redis (Caching/Queue).
- **Infrastructure**: Docker Compose, Caddy (Reverse Proxy/HTTPS).
- **Automation**: n8n (Workflow automation, Invoicing sync).
- **Payments**: Cashfree (Subscription and payment processing).
- **Messaging**: Telegram Bot API (Alerts and remote actions).

## Domains
- **Factory Management**: Multi-tenant onboarding, settings, and identity.
- **Production**: Machine tracking, shift output, and production logs.
- **Inventory**: Raw material and finished goods tracking.
- **Sales & CRM**: Customer management, sales entry, and outstanding balances.
- **Billing**: Subscription lifecycle, tax invoices, and payment collection.
- **Intelligence**: Deterministic cost-per-cup (CPC) engine and factory health snapshots.

## Deployment Process
Managed via `deploy.sh` on a Hostinger VPS:
1. **Pre-flight**: Validate working tree (no uncommitted changes).
2. **Backup**: Create timestamped `pg_dump -Fc` backup in `storage/backups/`.
3. **Schema**: Apply Alembic migrations.
4. **Rebuild**: Recreate containers (`api`, `web`, `caddy`).
5. **Verification**: Health check via `https://munshiai.co.in/api/health`.

## User Roles
- **Super Admin**: System-wide oversight, factory management, and audit logs.
- **Owner**: Full control over a specific factory, billing, and staff management.
- **Sub-Owner**: High-level operational control, similar to Owner but restricted from some billing/staff settings.
- **Supervisor**: Manages production and attendance, can enter sales.
- **Operator**: Entry-level data entry for production and inventory.

## Major Modules
- **Cost Engine**: Computes deterministic daily cost totals and weighted Cost Per Cup (CPC).
- **Telegram Action Layer**: Allows owners to trigger ERP actions and receive alerts via Telegram.
- **Bulk Onboarding**: Excel-based import for factories, staff, and machines with deterministic upsert logic.
- **Sales & Invoicing**: Server-side PDF generation (ReportLab) for sales invoices.

## Pricing Model
- **Subscription-based**: Tiered plans with trial periods.
- **Lifecycle**: Trial Active -> Trial Expired -> Active (Paid) -> Past Due/Expired.
- **Automation**: Cashfree webhooks drive the subscription state transitions.

## Telegram Integration Summary
- **Binding**: User-level binding (`telegram_user_bindings`) allowing multiple accounts (Owner/Sub-Owner) per factory.
- **Communication**: Bot-driven alerts (Cost spikes, Daily briefings) and Interactive buttons for remote ERP actions.
- **Security**: Binding codes for secure account linkage.
