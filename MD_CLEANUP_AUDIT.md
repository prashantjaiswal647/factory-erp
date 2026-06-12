# MD Documentation Cleanup Audit

This document lists all markdown (`.md`) files found in the Munshi AI repository, categorizes them according to the cleanup strategy, and guides the consolidation process.

| File | Keep / Merge / Archive / Delete Candidate | Reason | Important Knowledge | Duplicate With | Suggested Target File |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`AGENTS.md`** | **KEEP** | Core operating notes for AI agents. P0 rule. | Agent operation notes, model constraints, production checklists. | None | N/A (Keep at root) |
| **`README.md`** | **KEEP** | Root project overview and setup guidelines. | Basic dev commands, project overview. | None | N/A (Keep at root) |
| **`PROJECT_MEMORY.md`** | **KEEP** | Essential overview of product domains, tech stack, and deploy flow. | High-level architecture, pricing model, app flow. | None | N/A (Keep at root) |
| **`CURRENT_STATUS.md`** | **KEEP** | Latest system status and pilot/production readiness. | Pilot Readiness status (currently 75-80%), blocker lists. | None | N/A (Keep at root) |
| **`ARCHITECTURE.md`** | **KEEP** | System architecture, flow descriptions, directories. | Core design decisions, microservices/integrations mapping. | None | N/A (Keep at root) |
| **`DECISIONS.md`** | **KEEP** | Architectural and business records. | Dynamic routing, auth mechanisms, redirect policies. | None | N/A (Keep at root) |
| **`MEMORY.md`** | **DELETE CANDIDATE** | Redundant. Reading order list. | Trivial reading sequence list. | `PROJECT_MEMORY.md`, `README.md` | `README.md` / `PROJECT_MEMORY.md` |
| **`env-checklist.md`** | **MERGE** | Production secrets rotation guidelines. | Secret keys list, generation commands, safety rules. | None | `DEPLOYMENT.md` |
| **`docs/disaster_recovery_drill_report.md`** | **MERGE** | Backup & recovery procedures. | Postgres dump commands, verification steps. | None | `DEPLOYMENT.md` |
| **`docs/n8n-generate-invoice-local-setup.md`** | **MERGE** | PDF generation setup and gotenberg Docker service. | Local Gotenberg PDF setup, n8n invoice document branches. | None | `ARCHITECTURE.md` |
| **`docs/inventory-v3.md`** | **MERGE** | Inventory categorization buckets. | Category mapping rules, `bucket` field classifications. | None | `ARCHITECTURE.md` |
| **`MUNSHI_6_MONTH_ROADMAP.md`** | **MERGE** | Month-by-month roadmap. | Monthly execution roadmap, milestones. | `MUNSHI_AI_PRIORITY_ROADMAP.md` | `ROADMAP.md` |
| **`MUNSHI_AI_PRIORITY_ROADMAP.md`** | **MERGE** | Priority-formula and phase definitions. | Product prioritization formula, phase definitions. | `MUNSHI_6_MONTH_ROADMAP.md` | `ROADMAP.md` |
| **`MANUAL.md`** | **MERGE** | User manual and testing instructions for v2.0 features. | UI walkthroughs, OEE controller, UPI payments checkout simulator. | None | `TESTING.md` |
| **`QA_EXECUTION_PLAN.md`** | **MERGE** | QA guidelines, verification checklists. | E2E flows, edge cases, script references. | None | `TESTING.md` |
| **`SMOKE_TEST_WORKBOOK.md`** | **MERGE** | Steps for local verification and checks. | Manual testing scenarios, steps to verify pages. | None | `TESTING.md` |
| **`PILOT_SYNTHETIC_SMOKE_REPORT.md`** | **MERGE** | Validation of production telemetry simulation. | Telemetry validation checks. | None | `TESTING.md` |
| **`docs/agent-context/route_role_matrix.md`** | **MERGE** | RBAC permission details. | Map of endpoints and allowed user roles. | None | `SECURITY_AUDIT_SUMMARY.md` |
| **`docs/agent-context/security_audit_report.md`** | **MERGE** | Security vulnerabilities re-audit details. | CORS, CSRF, JWT security boundaries. | None | `SECURITY_AUDIT_SUMMARY.md` |
| **`AI_SUPERVISOR_V1.md`** | **ARCHIVE** | Historical spec of the AI Supervisor V1. | AI supervisor specification parameters. | None | `docs/archive/AI_SUPERVISOR_V1.md` |
| **`docs/testsprite-prd.md`** | **ARCHIVE** | PRD format checklist. | Test target lists and user roles. | None | `docs/archive/testsprite-prd.md` |
| **`ALEMBIC_0026_UNIFIED_ALERTS_FIX_REPORT.md`** | **ARCHIVE** | Single-sprint implementation report. | Alembic migration fix history. | None | `docs/archive/` |
| **`ALEMBIC_0027_INVOICE_DELIVERY_FIX_REPORT.md`** | **ARCHIVE** | Single-sprint implementation report. | Invoice delivery fix details. | None | `docs/archive/` |
| **`ARCHITECT_REVIEW.md`** | **ARCHIVE** | Session feedback snapshot. | Review notes. | None | `docs/archive/` |
| **`BILLING_PLANS_PRODUCTION_FIX_REPORT.md`** | **ARCHIVE** | Bug-fix implementation report. | Subscription logs. | None | `docs/archive/` |
| **`BREAKDOWN_LOG_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Machinery logging. | None | `docs/archive/` |
| **`BRIEFING_SNAPSHOTS_MIGRATION_FIX_REPORT.md`** | **ARCHIVE** | Implementation report. | Migration logs. | None | `docs/archive/` |
| **`BULK_DELETE_IMPLEMENTATION_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Bulk delete details. | None | `docs/archive/` |
| **`CI_SECURITY_TEST_FIX_REPORT.md`** | **ARCHIVE** | Pipeline validation report. | GitHub Actions CI secrets setup. | None | `docs/archive/` |
| **`DAILY_BRIEFING_HISTORY_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Daily briefing records. | None | `docs/archive/` |
| **`DAILY_BRIEFING_IMPLEMENTATION_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Briefing template logic. | None | `docs/archive/` |
| **`FACTORY_DELETE_CASCADE_REPORT.md`** | **ARCHIVE** | Cascade delete flow report. | Delete relationship cascades. | None | `docs/archive/` |
| **`FACTORY_DELETE_RELATIONSHIP_MAP.md`** | **ARCHIVE** | Visual DB mapping documentation. | DB references mapping. | None | `docs/archive/` |
| **`FINAL_PRODUCTION_CERTIFICATE.md`** | **ARCHIVE** | Historical task certification. | Production release certification. | None | `docs/archive/` |
| **`FIX_IMPLEMENTATION_REPORT.md`** | **ARCHIVE** | Implementation notes. | Code fixes detail. | None | `docs/archive/` |
| **`INVOICE_INTELLIGENCE_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Branded GST logic notes. | None | `docs/archive/` |
| **`P4_5_FINALIZATION_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Dev notes. | None | `docs/archive/` |
| **`P4_5_LIFECYCLE_FIX_REPORT.md`** | **ARCHIVE** | Implementation report. | Bug fix logs. | None | `docs/archive/` |
| **`P4_5_TELEGRAM_COMPLETION_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Telegram actions. | None | `docs/archive/` |
| **`P4_5_TEST_INFRA_FIX_REPORT.md`** | **ARCHIVE** | Infrastructure fix report. | Test suite repairs. | None | `docs/archive/` |
| **`PASSWORD_FEATURE_IMPLEMENTATION_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Staff password encryption. | None | `docs/archive/` |
| **`PILOT_FACTORY_SIMULATION_REPORT.md`** | **ARCHIVE** | Test run results. | Simulated factory output. | None | `docs/archive/` |
| **`PRODUCTION_TELEGRAM_ROOT_CAUSE_REPORT.md`** | **ARCHIVE** | Incident analysis. | Telegram webhook error log. | None | `docs/archive/` |
| **`REAL_FACTORY_LIFECYCLE_REPORT.md`** | **ARCHIVE** | Testing summary. | Live factory data test results. | None | `docs/archive/` |
| **`RECOVERY_AUTOMATION_REPORT.md`** | **ARCHIVE** | Automation report. | Disaster recovery auto-scripts. | None | `docs/archive/` |
| **`RELEASE_BLOCKER_MATRIX.md`** | **ARCHIVE** | Historical release status. | Bug triage matrix. | None | `docs/archive/` |
| **`SECURITY_HARDENING_REPORT.md`** | **ARCHIVE** | Security report. | Security patches details. | None | `docs/archive/` |
| **`STABILITY_REPORT.md`** | **ARCHIVE** | System check results. | Database checks logs. | None | `docs/archive/` |
| **`STAFF_MANAGEMENT_IMPLEMENTATION_REPORT.md`** | **ARCHIVE** | Feature implementation report. | User management setup. | None | `docs/archive/` |
| **`STAFF_WORKER_SAVE_BUG_REPORT.md`** | **ARCHIVE** | Bug analysis. | Worker validation issue details. | None | `docs/archive/` |
| **`STAFF_WORKER_SAVE_FIX_REPORT.md`** | **ARCHIVE** | Bug fix report. | Save bug repairs. | None | `docs/archive/` |
| **`SUPER_ADMIN_IMPLEMENTATION_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Super Admin CRUD endpoints. | None | `docs/archive/` |
| **`SUPER_ADMIN_MODIFICATION_REPORT.md`** | **ARCHIVE** | Feature implementation report. | Mod actions logs. | None | `docs/archive/` |
| **`SUPPORT_TICKET_REDUCTION_REPORT.md`** | **ARCHIVE** | Optimization report. | Bug prevention methods. | None | `docs/archive/` |
| **`TELEGRAM_BINDING_AND_MENU_FIX_REPORT.md`** | **ARCHIVE** | Bug fix report. | Telegram menus code details. | None | `docs/archive/` |
| **`TELEGRAM_COMMAND_CENTER_REPORT.md`** | **ARCHIVE** | Feature implementation report. | command center routing. | None | `docs/archive/` |
| **`TELEGRAM_SELF_SERVICE_FINAL_FIX_REPORT.md`** | **ARCHIVE** | Bug fix report. | Menu flow validations. | None | `docs/archive/` |
| **`TELEGRAM_WEBHOOK_MANAGER_CI_FIX_REPORT.md`** | **ARCHIVE** | Pipeline fix report. | Telegram CI variables setup. | None | `docs/archive/` |
| **`UX_POLISH_REPORT.md`** | **ARCHIVE** | UI update report. | Design feedback and changes. | None | `docs/archive/` |
| **`docs/agent-context/e2e_integration_test_report.md`** | **ARCHIVE** | Snapshot test results. | E2E check logs. | None | `docs/archive/` |
| **`docs/agent-context/expanded_test_coverage_report.md`** | **ARCHIVE** | Snapshot test results. | Expanded coverage summary. | None | `docs/archive/` |
| **`docs/agent-context/production_readiness_audit.md`** | **ARCHIVE** | Launch checklist status. | Audit matrices. | None | `docs/archive/` |
| **`docs/agent-context/test_guardian_report.md`** | **ARCHIVE** | CI validation report. | Test coverage safeguards. | None | `docs/archive/` |
