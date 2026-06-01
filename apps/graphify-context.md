Markdown
# 🌐 Cosmic Yog ERP - System Graphify Matrix

## 1. Monorepo Service Nodes (File Tree Connection)
- **Root Directory:** `~/factory-erp`
  - `docker-compose.yml` -> Manages system containers network topology.
  - `apps/` -> Contains modular application codebases.
    - `api/` -> **FastAPI Backend Cluster**
      - `routes/` -> Endpoint configurations (`workers.py`, `activity_logs.py`).
      - `models.py` -> SQLAlchemy DB relational schemas.
    - `web/` -> **React + Vite Frontend Client**
      - `src/pages/` -> Views (`OperationsPage.tsx`, `DailySequence.tsx`).
      - `src/components/` -> Modal controllers & form states.

## 2. Structural Data & Pipeline Flow Map
                    +---------------------------------------------+
                    |              React Frontend                 |
                    |    (Dashboard, Operations, Daily Sequence)   |
                    +------------------+--------------------------+
                                       |
                                       | (REST APIs via Nginx / VPS IP)
                                       v
                    +---------------------------------------------+
                    |               FastAPI Backend               |
                    |    (Auth, Multi-Tenancy Guard, Routing)     |
                    +---+------------------+------------------+---+
                        |                  |                  |
         (SQL Queries)  |                  | (Redis Cache)    | (Async Webhooks)
                        v                  v                  v
+---------------------------+        +---------------+  +---------------+

PostgreSQL Database    +        +  Redis Cache  +  +  n8n Engine   +

(With factory_id Indices) +        + (Dashboard UI)+  + (PDF/Img/Voice)+
+---------------------------+        +---------------+  +-------+-------+
|
v
+---------------+
|   OpenClaw    |
|  (AI Gateway) |
+---------------+


## 3. Database Entity Node Dependencies (SQLAlchemy)
- **Tenant Isolation Parameter:** Every query MUST explicitly filter on `factory_id`.
- **Worker Node:** `Worker` schema properties -> `id`, `factory_id` (Indexed), `name`, `phone_number`, `is_active`, `opening_attendance_count` (Previous Attendance balance).
- **Audit Logging Node:** `DailySequenceLog` schema properties -> `id`, `factory_id` (Indexed), `user_id`, `user_role`, `short_statement`, `timestamp`.

## 4. Active API Route Endpoints
- **Manual Operations Path:** `GET/POST` -> `/api/operations` (For manual row mutations).
- **Automated Sequence Path:** `GET` -> `/api/activity-logs/daily-sequence?date=YYYY-MM-DD` (Fetches short summary audit stream).
- **Profile Mutation Path:** `PUT` -> `/api/workers/{worker_id}` (Updates identity data & updates