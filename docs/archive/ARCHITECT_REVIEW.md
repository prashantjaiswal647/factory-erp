# Architect Review: Munshi AI

## 1. Current Strengths
- **Strong Multi-tenancy**: The use of a `TenantMixin` and strict `factory_id` scoping provides a reliable foundation for SaaS scaling.
- **Deterministic Intelligence**: The Cost Engine's approach to weighted CPC and daily snapshots avoids "AI hallucination" in financial reporting.
- **Robust Deployment**: `deploy.sh` includes essential safety gates (backups, validation) that prevent catastrophic production failures.
- **Clean Separation**: Service-layer pattern in the API allows for easier testing and business logic isolation.

## 2. Technical Debt
- **Model Duplication**: Overlapping models (e.g., `Employee` vs `Worker`) create confusion and risk data inconsistency. This is a high-priority cleanup task.
- **Frontend Route Guarding**: Some RBAC logic is duplicated or slightly drifted between the frontend and backend.
- **Local Storage JWT**: Storing sensitive tokens in `localStorage` exposes the app to XSS attacks.

## 3. Security Concerns
- **Secret Leakage**: History of exposed keys in transcripts/logs; requires a strict rotation policy and `.env` auditing.
- **Error Leakage**: Some endpoints may still leak internal Python exception strings to the client (being addressed in P0).
- **CORS/Origins**: Needs strict verification of production origins to prevent unauthorized API access.

## 4. Scaling Concerns
- **DB Connections**: Without pgBouncer, the API will hit PostgreSQL connection limits quickly as the number of factories grows.
- **Observability**: Lack of centralized logging and monitoring (Prometheus/Grafana/Sentry) makes debugging production incidents reactive rather than proactive.
- **State Management**: Heavy reliance on `localStorage` for state; needs a more robust session management strategy.

## 5. Deployment Concerns
- **Caddy Complexity**: The routing contract between Vite and Caddy (trailing slashes, API redirects) is brittle and requires careful synchronization during deploys.
- **Backup Volume**: Backups are stored locally on the VPS; needs off-site backup (S3/Cloud Storage) for true Disaster Recovery.

## 6. Telegram Architecture Review
- **Binding Model**: The move to user-level bindings is correct and allows for scalable role-based access.
- **Reliability**: Action alerts are currently "best-effort"; a failed Telegram notification should not block an ERP transaction, which is correctly implemented.
- **Isolation**: Currently lacks strict channel-based isolation for different roles; all alerts flow through a single bot interaction.

## 7. Recommended Next 10 Sprints
1. **P0 Stabilization**: CI fix, Error sanitization, Secret rotation.
2. **Bulk Upload Hardening**: Idempotency and Validation UI.
3. **RBAC Alignment**: Sync frontend/backend guards and cleanup sidebar URLs.
4. **Model Consolidation (Part 1)**: Migrate `Employee` $\rightarrow$ `Worker` with compatibility layer.
5. **Model Consolidation (Part 2)**: Merge `Expense` and `Stock` model families.
6. **Audit Trail**: Build the Owner-facing review UI for activity logs.
7. **Security Hardening**: Migrate JWT to HttpOnly Cookies.
8. **DR Validation**: Full production restore drill and off-site backup setup.
9. **Performance**: Implement pgBouncer and Redis caching for frequent lookups.
10. **Observability**: Deploy a basic monitoring stack (Uptime Kuma + Sentry).
