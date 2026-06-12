# Architecture: Munshi AI

## System Architecture
High-level flow:
`User Browser` <--> `Caddy (HTTPS/Reverse Proxy)` <--> `FastAPI (Backend)` <--> `PostgreSQL / Redis`
                                             |--> `React (Frontend Static Assets)`
                                             |--> `n8n (Automation)`

## User Hierarchy
1. **Super Admin** (Global)
   └── **Owner** (Factory)
       └── **Sub-Owner** (Factory)
           └── **Supervisor** (Factory)
               └── **Operator** (Factory)

## ERP Workflow
1. **Onboarding**: Bulk Excel upload -> Factory/Staff/Machine creation.
2. **Daily Operations**: 
   - Attendance -> Production Entry -> Inventory Deduction.
   - Sales Entry -> Customer Balance Update -> Invoice Generation.
3. **Intelligence**: 
   - Daily Totals -> Cost Engine -> Weighted CPC.
   - Health Snapshots -> Morning Briefing -> Telegram Alert.

## Telegram Workflow
`Telegram User` <--> `Bot API` <--> `Telegram Action Layer (FastAPI)` <--> `ERP Service` <--> `Database`
- **Alerts**: Triggered by schedulers/events -> Sent via `telegram_delivery.py`.
- **Actions**: Inline Button -> Callback -> `telegram_actions.py` -> DB Update.

## Data Flow
`Request` $\rightarrow$ `JWT Auth Middleware` $\rightarrow$ `Tenant Context (factory_id)` $\rightarrow$ `Router` $\rightarrow$ `Service Layer` $\rightarrow$ `SQLAlchemy Model` $\rightarrow$ `PostgreSQL`

## Database Overview
- **Pattern**: Shared Database, Shared Schema (Multi-tenancy via Discriminator).
- **Key Column**: `factory_id` (Present in almost every table via `TenantMixin`).
- **Integrity**: Strict `CheckConstraints` for roles, subscription statuses, and non-negative values.
- **Migrations**: Managed via Alembic with mandatory pre-migration backups.

## n8n & Gotenberg Integration Overview
- **Role**: External workflow engine for asynchronous/complex tasks.
- **Invoice PDF Flow**: Local n8n instances (port `5678`) communicate internally via the Docker network with a `gotenberg` service (port `3000`) utilizing `chromium` to convert raw HTML into legal invoices and optional parallel rough bills. PDFs are written to `storage/invoices/invoice_<factory_id>_<invoice_id>.pdf`.
- **Use Cases**: 
  - Invoice synchronization.
  - External data triggers.
  - Complex alerting pipelines.
- **Auth**: Secured via `X-N8N-API-KEY`.

## Live Inventory Buckets (Inventory v3)
Categorization maps the backend `bucket` field as the sole source of truth on the Live Inventory page:
- `cup_blanks` (Raw Cup Blanks)
- `bottom_reels` (Bottom Reels)
- `finished_goods` (Finished Goods)
- `polybags_packing` (Packaging)
- `boxes` (Boxes)
- `raw_other` (General raw material fallback for `Raw` category)
- `needs_mapping_review` (Any category mismatch/unknown classification)

All stock operations and API routes are strictly partitioned using the user's authenticated `factory_id`.

