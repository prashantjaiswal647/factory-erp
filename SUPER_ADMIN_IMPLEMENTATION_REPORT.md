# SUPER ADMIN IMPLEMENTATION REPORT

## Summary

Implemented a hidden Munshi AI Super Admin control room for platform-owner use only.

Frontend hidden route:

```text
/munshi-control-room
/munshi-control-room/dashboard
/munshi-control-room/owners
/munshi-control-room/factories
/munshi-control-room/factories/:factoryId
/munshi-control-room/subscriptions
/munshi-control-room/payments
/munshi-control-room/audit-logs
```

Backend API prefix:

```text
/api/super-admin
```

The route is not linked from the public homepage, normal sidebar, dashboard menu, navbar, or footer.

## Backend API Endpoints Added

```text
POST   /api/super-admin/login
GET    /api/super-admin/me
GET    /api/super-admin/dashboard

GET    /api/super-admin/owners
GET    /api/super-admin/owners/{owner_id}
PATCH  /api/super-admin/owners/{owner_id}
PATCH  /api/super-admin/owners/{owner_id}/status

GET    /api/super-admin/factories
POST   /api/super-admin/factories
GET    /api/super-admin/factories/{factory_id}
PATCH  /api/super-admin/factories/{factory_id}
DELETE /api/super-admin/factories/{factory_id}

GET    /api/super-admin/subscriptions
PATCH  /api/super-admin/subscriptions/{subscription_id}
POST   /api/super-admin/subscriptions/manual-adjustment

GET    /api/super-admin/payments
PATCH  /api/super-admin/payments/{payment_id}
POST   /api/super-admin/payments/manual-entry

GET    /api/super-admin/audit-logs
```

## Authentication And Security

Super admin authentication is separate from normal factory-owner authentication.

Required backend environment variables:

```text
SUPER_ADMIN_EMAIL=
SUPER_ADMIN_PASSWORD_HASH=
SUPER_ADMIN_JWT_SECRET=
```

The frontend never hardcodes the password and stores the super-admin token in:

```text
sessionStorage["munshi_super_admin_token"]
```

Normal owner tokens are not accepted by `/api/super-admin/*` because the backend requires a separate JWT signed with `SUPER_ADMIN_JWT_SECRET` and containing:

```text
role=super_admin
scope=super_admin
sub=SUPER_ADMIN_EMAIL
```

All `/api/super-admin/*` endpoints except login require this token. Unauthorized requests return `401` or `403`.

Passwords are verified against `SUPER_ADMIN_PASSWORD_HASH`; no plaintext password is stored in code.

To generate a hash safely on the VPS:

```text
docker compose run --rm api python -c "from auth import hash_password; print(hash_password('REPLACE_WITH_STRONG_PASSWORD'))"
```

Do not commit the plaintext password.

## Database Changes

Added model/table:

```text
super_admin_audit_logs
```

Fields:

```text
id
admin_email
action_type
entity_type
entity_id
old_value JSONB
new_value JSONB
note
ip_address
created_at
```

Added factory columns through startup-safe SQL:

```text
factories.usage_limit INTEGER
factories.admin_note TEXT
```

Existing fields reused:

```text
users.role
users.is_active
users.last_login_at
factories.plan_name
factories.active_plan
factories.subscription_status
factories.payment_status
factories.billing_cycle
factories.trial_start_date
factories.trial_end_date
factories.subscription_start_date
factories.subscription_end_date
factories.plan_expires_at
subscription_payments
```

No production payment gateway integration was added.

## Audit Logging

Audit logs are created for:

```text
owner update
owner enable/disable
factory create/update/delete
subscription update
manual subscription adjustment
payment update
manual payment entry
```

## Frontend UI Added

Pages:

```text
SuperAdminLoginPage
SuperAdminDashboardPage
SuperAdminOwnersPage
SuperAdminFactoriesPage
SuperAdminFactoryDetailPage
SuperAdminSubscriptionsPage
SuperAdminPaymentsPage
SuperAdminAuditLogsPage
```

Features implemented:

```text
separate login page
protected control-room shell
dashboard metrics
owners table with search and enable/disable action
factories table with search
factory detail summary with counts
subscription list and manual edit modal
payments table
audit logs table
```

Manual subscription edits require browser confirmation and create audit logs.

## Playwright Tests Added

Local tests:

```text
hidden admin route is not visible in normal navigation
unauthenticated protected admin route redirects to admin login
normal factory owner session cannot access super admin dashboard
super admin can login and open protected pages
```

The authenticated super-admin test is skipped unless these env vars are set:

```text
PLAYWRIGHT_SUPER_ADMIN_EMAIL=
PLAYWRIGHT_SUPER_ADMIN_PASSWORD=
```

Production smoke tests:

```text
admin login page loads
protected admin route blocks anonymous access
authenticated smoke only runs if super-admin env credentials are supplied
```

## Files Changed

```text
apps/api/main.py
apps/api/models.py
apps/api/routers/super_admin.py
apps/web/.env.example
apps/web/src/App.tsx
apps/web/src/lib/api.ts
apps/web/src/pages/SuperAdminPages.tsx
apps/web/e2e/tests/local/super-admin.spec.ts
apps/web/e2e/tests/production/super-admin-smoke.spec.ts
```

Related existing E2E/report files in this branch also include previous subscription/UX fixes.

## Verification

Frontend build:

```text
npm run build
passed
```

Backend tests:

```text
docker compose run --rm api python -m pytest tests
32 passed
```

Local Playwright:

```text
PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:local
26 passed
1 skipped
```

UX Playwright:

```text
PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:ux
14 passed
```

Note: `5174` was used locally because port `5173` is occupied on this machine.

## Manual Testing Steps

1. Configure backend env:

```text
SUPER_ADMIN_EMAIL=admin@example.com
SUPER_ADMIN_PASSWORD_HASH=<bcrypt hash>
SUPER_ADMIN_JWT_SECRET=<long random secret>
```

2. Rebuild/restart backend:

```text
docker compose build api
docker compose up -d api
```

3. Open manually:

```text
http://localhost:5173/munshi-control-room
```

4. Login with super-admin credentials.

5. Verify:

```text
/munshi-control-room/dashboard
/munshi-control-room/owners
/munshi-control-room/factories
/munshi-control-room/subscriptions
/munshi-control-room/payments
/munshi-control-room/audit-logs
```

6. Perform a test subscription edit and verify `/munshi-control-room/audit-logs` records it.

## Production Smoke After Deploy

Do not run before deployment.

```text
PLAYWRIGHT_BASE_URL=https://munshiai.co.in npm run test:e2e:prod
```

Optional authenticated production smoke:

```text
PLAYWRIGHT_BASE_URL=https://munshiai.co.in PLAYWRIGHT_SUPER_ADMIN_EMAIL=... PLAYWRIGHT_SUPER_ADMIN_PASSWORD=... npm run test:e2e:prod
```

## Remaining Limitations

The current UI provides core management workflows and backend endpoints for all requested admin actions. Some advanced actions are endpoint-backed but intentionally minimal in UI:

```text
factory create/edit/delete UI can be expanded beyond the current list/detail workflow
payment manual-entry UI can be expanded beyond the current table view
reset password was not implemented because a safe email/OTP reset pipeline was not in scope
usage/tokens are shown as zero unless a real usage tracking table is later added
```

Payment gateway integration was intentionally not added.
