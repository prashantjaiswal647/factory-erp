# Munshi AI Security Audit Summary

This document consolidates findings from security re-audits, RBAC alignments, CORS rules, and rate limits.

---

## 1. Security Risk Matrix & Patch Status

All historical vulnerabilities have been triaged. Below is the active status map of resolved and open issues:

| Risk ID | Category | Description | Severity | Status | Verification / Mitigation Detail |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | Webhooks | AI Webhook endpoint `/api/ai/n8n-webhook` exposed context with no auth. | **P0** | **FIXED** | Secured via `X-N8N-API-KEY` validation header check. |
| **SEC-02** | Customer Portal | Storefront order views allowed access via URL token only. | **P1** | **FIXED** | Uses signed, short-lived storefront session token constraints. |
| **SEC-03** | Secrets | Insecure default fallback secret for `N8N_API_KEY` in code. | **P1** | **FIXED** | Fallback removed; fails safe by raising a 503 HTTP status. |
| **SEC-04** | Auth JWT | JWT access tokens had a lifetime default of 30 days. | **P1** | **FIXED** | Token validity reduced to a secure 8-hour window (480 mins). |
| **SEC-05** | Rate Limit | Storefront login verification lacked rate-limiting. | **P1** | **FIXED** | Sliding window rate limiter (5 req/min) enforced per IP. |
| **SEC-06** | RBAC | Tenant owners allowed to approve global machine templates. | **P1** | **FIXED** | Approval restricted strictly to Super Admin endpoints. |
| **SEC-07** | Cryptography | Cryptographic fallback key used in `telegram_crypto.py`. | **P2** | **FIXED** | Raises a `RuntimeError` on startup if `JWT_SECRET_KEY` is missing. |
| **SEC-08** | Debug Logs | Debug prints (`print("AUTH DEBUG: ...")`) dump identifiers to stdout. | **P2** | **OPEN** | Strip credentials; logs need standard logging module sanitizers. |
| **SEC-09** | JWT Storage | Frontend stores JWT tokens in client-side `localStorage`. | **P2** | **OPEN** | Architectural risk. Migrate to secure HTTP-only cookies in later phase. |
| **SEC-10** | RBAC | Workers/Operators had read/write access to factory expenses. | **P2** | **FIXED** | Access restricted to Owner and Supervisor roles. |
| **SEC-11** | RBAC | Operators could write machine onboarding settings. | **P2** | **FIXED** | Restricted onboarding configuration to Owner/Supervisor. |
| **SEC-12** | Super Admin | Super Admin login lacks rate-limiting. | **P2** | **OPEN** | Limit login attempts via Caddy/slowapi rate-limit filters. |

---

## 2. Route Role RBAC Matrix

To prevent authorization drift, frontend sidebar visibility guards and backend FastAPI dependencies are aligned as follows:

| Route | Backend Endpoint | Allowed Backend Roles | Allowed Frontend Roles | Status |
| :--- | :--- | :--- | :--- | :--- |
| `/daily-sequence` | `routers/operations.py` | Owner, Sub-Owner, Supervisor, Operator | Owner, Sub-Owner, Supervisor, Operator | Aligned |
| `/operations` | `routers/operations.py` (Mutations) | Owner, Sub-Owner (Edit/Delete); Supervisor (Read-only where allowed) | Owner, Sub-Owner | Aligned for mutations |
| `/expenses` | `routers/expenses.py` | Owner, Sub-Owner, Supervisor | Owner, Sub-Owner, Supervisor | Restricted (Operator/Worker blocked) |
| `/machine-onboardings` | `routers/machines.py` | Owner, Sub-Owner, Supervisor | Owner, Sub-Owner, Supervisor | Restricted (Operator/Worker blocked) |

### RBAC Constraints:
- Backend and frontend RBAC permissions must always be updated together.
- Never write absolute production URLs for internal paths in frontend navigations; always use relative routes (e.g., `/operations`).
- If backend grants read access to a role, the frontend should not hide the option unless explicitly signed off by the platform lead.

---

## 3. Webhook and Portal Guardrails

### CORS Policy:
- Wildcard domains are explicitly disabled when credentials are active. Access is allowed only for origins listed under the environment values `CORS_ORIGINS`, `FRONTEND_ORIGIN`, and target deployment hosts.

### Storefront CSRF Policy:
- Storefront sessions are verified via an `HttpOnly` cookie with `samesite="lax"`. Operations are REST APIs requiring validation headers (`X-Storefront-Session`), which protects the interface from traditional form-based cross-origin request forgery.

---
**Source Files Compressed:** `docs/agent-context/route_role_matrix.md`, `docs/agent-context/security_audit_report.md`
