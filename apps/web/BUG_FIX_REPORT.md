# BUG FIX REPORT

## Production Bug

Observed failures:

```text
404 GET /api/v1/dashboard/subscription-status
Error fetching subscription: AxiosError: Request failed with status code 404
Dashboard heading not found: Live Factory Overview
```

## Route Map And Debug Evidence

Frontend search found the old executable subscription-status call in:

```text
apps/web/src/components/Layout.tsx
apps/web/src/lib/api.ts
```

The old frontend call was:

```text
GET /api/v1/dashboard/subscription-status
```

Backend search found the matching local FastAPI route:

```text
apps/api/routers/dashboard.py
@v1_router.get("/subscription-status", response_model=DashboardSubscriptionStatus)
```

The router is locally included in:

```text
apps/api/main.py
app.include_router(dashboard.v1_router)
```

Local unauthenticated API evidence:

```text
GET http://localhost:8000/api/v1/dashboard/subscription-status
status=401

GET http://localhost:8000/api/v1/users/me/subscription
status=401

GET http://localhost:8000/api/billing/plans
status=200
```

The local `401` means the route exists locally and is protected. The production `404` therefore points to stale deployed backend code or a production proxy/backend route mismatch.

Expected authenticated subscription response contains:

```text
access_allowed
days_left
plan_name
subscription_status
payment_status
effective_plan
effective_status
effective_expires_at
server_time
```

## Root Cause

The frontend was tightly coupled to `/api/v1/dashboard/subscription-status`. Production returned `404` for that endpoint, so the layout logged `Error fetching subscription` and did not have a graceful visible fallback.

The dashboard heading was missing when the dashboard itself replaced the full page with an error block. That happened because `DashboardPage` used `Promise.all()` for all dashboard data. One failed or timed-out dashboard request could prevent the `Live Factory Overview` heading from rendering.

The heading text has not intentionally changed.

## Fix Implemented

The frontend layout now uses the canonical DB-backed subscription endpoint:

```text
GET /api/v1/users/me/subscription?t={Date.now()}
```

The layout derives warning-banner and lock state from that response. It no longer calls `/api/v1/dashboard/subscription-status`.

If the canonical subscription endpoint fails, the dashboard is not blocked. The navbar renders:

```text
Subscription status unavailable
```

The dashboard now uses `Promise.allSettled()` for dashboard data. Available data renders even if one non-auth request fails, and a warning message appears instead of a blank/error-only dashboard.

## Before / After Routes

Before:

```text
GET /api/v1/users/me/subscription?t={Date.now()}
GET /api/v1/dashboard/subscription-status
```

After:

```text
GET /api/v1/users/me/subscription?t={Date.now()}
```

Backend route still exists locally:

```text
GET /api/v1/dashboard/subscription-status
```

## Stable Selectors Added

```text
data-testid="dashboard-heading"
data-testid="subscription-status-card"
data-testid="subscription-fallback-message"
```

## Files Changed

```text
apps/web/src/components/Layout.tsx
apps/web/src/pages/DashboardPage.tsx
apps/web/src/lib/api.ts
apps/web/e2e/fixtures/diagnostics.ts
apps/web/e2e/pages/DashboardPage.ts
apps/web/e2e/tests/local/auth-flow.spec.ts
apps/web/e2e/tests/ux/navigation-ux.spec.ts
apps/web/package.json
apps/web/BUG_FIX_REPORT.md
```

## Tests Added / Updated

Added local E2E tests:

```text
dashboard loads with subscription fallback when subscription API returns 404
dashboard loads with subscription fallback when subscription API returns 500
```

These verify:

```text
dashboard heading remains visible
subscription fallback message appears
legacy /api/v1/dashboard/subscription-status is not called by the frontend
no Error fetching subscription / AxiosError console regression is emitted
```

Updated the dashboard page object to locate the heading by `data-testid="dashboard-heading"`.

Updated UX navigation test to use the shared dashboard-ready assertion after browser back navigation.

## Commands Run And Results

Build:

```text
npm run build
passed
```

Local E2E:

```text
PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:local
23 passed
```

UX E2E:

```text
PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:ux
14 passed
```

Backend pytest:

```text
docker compose run --rm api python -m pytest tests
32 passed
```

Note: `http://localhost:5174` was used because port `5173` is occupied on this machine.

## Remaining Known Issues

No remaining blocking issue for this bug.

Production smoke was not run because deployment was explicitly out of scope. After pushing and deploying, run:

```text
PLAYWRIGHT_BASE_URL=https://munshiai.co.in npm run test:e2e:prod
```

## Deployment Note

After pulling on the VPS, rebuild/restart the app normally:

```text
docker compose build api
docker compose up -d api
```
