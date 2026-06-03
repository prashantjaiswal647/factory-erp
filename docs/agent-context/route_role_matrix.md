# Route Role Matrix

Current pilot-readiness route alignment notes.

| Route | Backend source | Backend roles | Frontend source | Frontend roles | Status |
|---|---|---|---|---|---|
| `/daily-sequence` | `apps/api/routers/operations.py` daily sequence read endpoints | Owner, Sub-Owner, Supervisor, Operator | `apps/web/src/App.tsx`, `apps/web/src/components/Layout.tsx` | Owner, Sub-Owner, Supervisor, Operator | Aligned |
| `/operations` | `apps/api/routers/operations.py` manual operations sequence mutation endpoints | Owner, Sub-Owner for edit/delete; read includes Supervisor where explicitly allowed | `apps/web/src/App.tsx`, `apps/web/src/components/Layout.tsx` | Owner, Sub-Owner | Aligned for manual edit surface |

Rules:
- Backend and frontend RBAC must be updated together.
- Internal app navigation must use router-relative paths, not production absolute URLs.
- If backend grants read access to a staff role, the frontend route and sidebar must not hide that read-only view unless the exception is documented here.
