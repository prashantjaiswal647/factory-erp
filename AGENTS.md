# Munshi AI - Master Project Context & AI Playbook

## Project Overview

Munshi AI is an AI-Powered Smart ERP / Factory Supervisor SaaS designed for paper cup and paper glass manufacturing units.

The goal is to digitize and automate factory operations, reduce manual bookkeeping, provide real-time business visibility, and gradually evolve into an AI Supervisor capable of monitoring production, inventory, finance, CRM, and factory operations.

---

## Current Readiness Status

* **Migrations**: Complete & Idempotent (Alembic baseline setup, runtime migrations removed)
* **Factory Isolation**: Verified (adversarial multi-tenant tests passing)
* **Security**: P0 = 0, P1 = 0 (secured webhooks, storefront sessions, rate limiting, and tightened RBAC)
* **Testing**: Active Expansion (69+ tests passing in the backend suite)
* **Pilot Deployment**: Approved (safe for first pilot factory onboarding)
* **AI Supervisor**: Future Phase (integrates with Groq/Gemma)

---

## Current Production Environment

### Live URLs
* **Dashboard**: [https://munshiai.co.in](https://munshiai.co.in)
* **API**: [https://munshiai.co.in/api](https://munshiai.co.in/api)
* **n8n**: [https://n8n.munshiai.co.in](https://n8n.munshiai.co.in)

---

## Technology Stack & Architecture

### Backend
* **FastAPI (Python)**: Application framework.
* **Alembic**: Database migration management.
* **SQLAlchemy**: ORM for database modeling.

### Frontend
* **React + Vite (TypeScript)**: Single Page Application client.

### Database
* **PostgreSQL**: Production database engine.

### Infrastructure & Reverse Proxy
* **Docker Compose**: Containerized multi-service runtime.
* **Caddy**: Reverse proxy managing SSL/TLS certificates and load routing.

### Automation
* **n8n**: Workflow automation for alerts, reports, and reminders.

---

## Multi-Tenant & Factory Isolation Rules

The entire system is multi-tenant. Factory isolation is mandatory.
* **Core Rule**: Every business record must belong to a specific factory. Never allow data leakage between factories.
* **Multi-Tenant Filter**: Every query, API, report, dashboard, inventory calculation, attendance record, order, invoice, production record, and financial transaction must remain isolated using the `factory_id` filter (managed in `tenant_context.py`).

---

## Authentication & Authorization (RBAC) Rules

### 1. Webhook Security
* All n8n/internal API automation endpoints (e.g., `/api/ai/n8n-webhook`, `/api/v1/internal/bot-lookup`) must require validation of the `X-N8N-API-KEY` header matching the `N8N_API_KEY` environment secret.
* Fallback default secrets in code are strictly prohibited. Endpoints must fail-closed (e.g., return `503 Service Unavailable` or `401 Unauthorized`) if production secrets are missing.

### 2. Token Security
* **Access Tokens**: Default JWT access token expiration is set to a secure 8-hour window (`ACCESS_TOKEN_EXPIRE_MINUTES = 480`) to limit token theft window.
* **Storefront Session Validation**: Storefront access requires a short-lived cryptographically signed token validated via `X-Storefront-Session` header or `storefront_session` cookie.

### 3. Role-Based Access Control (RBAC) Boundaries
* **Super Admin**: Manual approval of global machine templates is a Super Admin-only action (uses `require_super_admin`).
* **Owner, Sub-Owner, Supervisor**: Permitted to manage machine onboarding settings, dynamic machine setups, list/view templates, and record/view expenses.
* **Operator & Worker**: Strictly blocked (returns `403 Forbidden`) from modifying machine onboarding settings, managing template approvals, and viewing or recording expenses.
* **Operator Exception**: Operators are permitted to query active dynamic machines (GET `/api/machines/active`) to select active machines when entering daily production logs.

---

## Database Migration Rules

* **No Startup Schema Modification**: Creating or altering tables during FastAPI startup or request handlers is prohibited.
* **Alembic Control**: All database schema changes must be version-tracked inside the `alembic/versions` directory.
* **Baseline Revision**: Revision `20260603_0001` serves as the initial runtime schema baseline.
* **Additive and Idempotent**: Migrations must be designed to safely execute on existing databases containing production data without drops.
* **Safe Rollbacks**: Downgrade routines must return `None` or not perform destructive column drops. System rollbacks are handled via PostgreSQL backup pre-migration checkpoints.

---

## Deployment & Backup Rules

### Deployment Workflow
Local Development → Testing → Git Commit → Git Push → Hostinger Pull → Docker Rebuild → Production Verification

Commands:
```bash
git add .
git commit -m "commit message"
git push origin main
```

VPS:
```bash
cd ~/factory-erp
git pull origin main
docker-compose up -d --force-recreate --build web api caddy
```

### Backup Pipelines
* Daily PostgreSQL database dumps are automatically triggered via `backup.sh`.
* Dump files are written to `/src/storage/backups`.
* Retention policy: Automatically prunes files older than 7 days.

---

## Testing & Quality Assurance Rules

Before modifying any code:
1. Run relevant tests.
2. Preserve factory_id isolation.
3. Preserve security controls.
4. Preserve migration compatibility.
5. Preserve SaaS multi-tenancy.

### Test Execution Commands
Always run the backend test suite with PYTHONPATH set:
```bash
$env:PYTHONPATH="apps/api"
python -m pytest apps/api/tests/
```

### Critical Verification Areas
* **E2E ERP Flow**: Validates inventory counts, sales invoices, collections, and deletions/reversals.
* **Factory Isolation**: Asserts zero data leakage between distinct factory datasets.
* **Bulk Upload Idempotency**: Ensures duplicate rows in Excel uploads are skipped, modified rows are updated, and new rows are inserted.
* **Salary Calculations**: Combines onboarding historical attendance and future daily logs to settle net wage payments.

---

## Known Remaining Risks (Audit Debt)

* **Super Admin Panel**: `/api/super-admin/login` has no rate-limiting or MFA protection.
* **Webhook Abuse**: Lacks rate-limit bounds on public n8n endpoints, introducing potential Groq API usage cost exhaustion.
* **Log Leakage**: Debug `print` logs in `auth.py` write user emails/phone numbers to standard stdout.
* **Client-Side Auth**: JWT tokens are stored in React client `localStorage` (XSS vector).

---

## Core Business Modules & Vision

### Factory Onboarding Module
* **Purpose**: Capture factory setup information and initialize the ERP.
* **Fields**: Factory details, product types, machine info, worker profiles, initial inventory, opening attendance, and opening financial balances.
* **Salary Integration**: Onboarding attendance history merges with daily logs. Salary calculation formula:
  `Past Onboarding Attendance + Future Daily Attendance = Final Salary Settlement`

### Inventory Module
* **Purpose**: Track all raw materials, consumables, packaging, and finished goods movement.
* **UI Constraint**: Display inventory category-wise without horizontal scrolling (Bottom, Blanks, Packaging, Finished Goods).
* **Inventory History**: Supports Stock In, Stock Out, Current Stock, Valuation, and audit history.

### Production Module
* **Purpose**: Track daily manufacturing output, wastage, and machines performance.
* **Business Logic**: Production directly affects inventory balances:
  `Raw Material Stock -> Wastage -> Finished Goods Stock`

### Wastage Module
* **Purpose**: Track production losses separately. Exposes machine-wise wastage and category-wise wastage logs for historical audits.

### Worker Management Module
* **Purpose**: Manage factory workforce, profile details, daily attendance, advance payments, and salary payroll calculations.

### Finance Module
* **Purpose**: Track purchases, expenses, sales, and collections. Provides P&L, cash flow tracking, and AI budget optimization suggestions in future phases.

### CRM & Order Management Module
* **Purpose**: Manage customer accounts, balances, payment terms, and invoice flows.
* **Order Flow**: Order Created -> Inventory Reserved -> Dispatch -> Invoice -> Payment Collection.

### Dispatch & Invoice Modules
* **Purpose**: Record finished goods shipments, auto-deduct inventory, and generate PDF invoices containing payment terms and QR codes.

### Payment Reminder Automation
* **Purpose**: Workflow in n8n queries outstanding dues and triggers WhatsApp alerts to customers with payment portal access links.

---

## SaaS Future Roadmap

1. **pgBouncer Integration**: Support high database request throughput connection pooling.
2. **Automated Payment Gateways**: Integrate Stripe or Razorpay webhooks to handle plan upgrades and automatic tenant locking.
3. **MFA Enforcements**: Enforce Multi-Factor Authentication on the Super Admin console.
4. **Log Sanitization**: Clean stdout prints to use Python logging.
5. **AI Supervisor Vision**: Evolve the LLM core using groq/gemma into a proactive manager monitoring costing, suggests purchase times, alerts on unusual wastage, and checks factory health indicators.
