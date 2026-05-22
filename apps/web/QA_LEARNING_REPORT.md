# QA LEARNING REPORT

This report summarizes patterns found while implementing and running the Munshi AI ERP Playwright tests.

## Test Runs Covered

Local full-flow:

```text
npm run test:e2e:local
21 passed
```

Production smoke:

```text
npm run test:e2e:prod
1 failed, 1 skipped
```

The production failure is documented in `BUG_REPORT.md` as `BUG-001`.

## Most Common Bug Patterns Found

### 1. Environment-specific API URL problems

The most important product bug was a production frontend calling `http://localhost:8000`.

Pattern:

```text
Works locally, fails on production.
```

Why it matters:
Localhost is valid during development but invalid for public users. In production, the browser treats `localhost` as the user's own computer.

How to catch it:
- Run production smoke tests from a real browser context.
- Capture failed network requests.
- Search diagnostics for `localhost`, `127.0.0.1`, `0.0.0.0`, and `http://` from `https://` pages.

### 2. Ambiguous selectors in automation

Three initial Playwright failures were caused by selectors matching multiple elements:

```text
Sign Up tab + Sign Up submit button
Login tab + Login submit button
Password + Confirm Password
```

Pattern:

```text
Common UI words appear more than once on the page.
```

How to catch it:
Playwright strict mode fails when a locator resolves to more than one element.

How to avoid it:
- Scope locators to a form, dialog, row, card, or page section.
- Use `{ exact: true }` for labels like `Password`.
- Prefer user-visible labels and roles, but make them precise.

### 3. Production smoke tests need different safety rules than local full-flow tests

Local tests can create test users and test records. Production tests should not create real business data unless a known test account is provided.

Pattern:

```text
Same app, different risk profile.
```

How to handle it:
- Local: run full signup and data mutation flows.
- Production: read-only smoke by default.
- Authenticated production tests should skip unless env credentials are provided.

## Frontend Weaknesses

### API base URL detection is fragile

Current production behavior indicates the frontend can fall back to local API URLs in live environments.

Recommended improvement:
Centralize environment resolution and make production fallback safe:

```text
if hostname is munshiai.co.in, API base should be same-origin or VITE_API_URL.
```

### Repeated button labels are common

The login/signup UI uses the same words for tabs and submit buttons.

This is fine for users, but tests need precise selectors.

Recommended improvement:
Keep accessible labels as-is, but add stable `data-testid` only where there is no reliable semantic selector.

### Some forms rely on custom validation messages

Examples:
- Signup invalid phone validation
- Profile invalid phone validation
- Factory expense required validation

Recommended improvement:
Standardize validation message placement so tests can find errors consistently.

## Backend Weaknesses

No backend functional bug was confirmed by the local Playwright run. The local signup, phone-only login, auth storage, dashboard data, protected route loading, and representative submit flows passed.

Areas that still need deeper backend testing:
- Subscription edge cases with expired/future trial dates.
- Multi-tenant isolation for staff users.
- Production/inventory/sales submissions with real dependent seed data.
- API authorization rules per role.

## Validation Weaknesses

The suite now verifies:
- Signup required fields.
- Invalid local mobile number.
- Profile invalid local mobile number.
- Factory expense required fields.

Recommended future validation tests:
- Duplicate phone signup.
- Duplicate email signup.
- Invalid email format.
- Password mismatch.
- Unsupported country code payload through API.
- Backend rejects malformed phone even if frontend is bypassed.
- Numeric fields reject negative values where business rules require positive quantities.

## Authentication Weaknesses

The suite verifies:
- Unauthenticated `/dashboard` redirects to `/login`.
- Signup creates an account locally.
- Login works using phone number only.
- Auth token/session values are stored.

Recommended future authentication tests:
- Invalid password shows a safe error.
- Expired JWT redirects to login.
- Logout clears `ai_erp_token`, `token`, `ai_erp_user`, and `factory_id`.
- Staff users cannot access Owner-only routes.
- Google signup completion requires mobile number and factory data.

## UX Issues

No blocking local UX issue was confirmed after test selector fixes.

Potential UX areas to inspect manually:
- The login/signup page has duplicate visible button names, which is understandable but can be confusing to automation.
- Validation messages should be visually consistent across pages.
- Production homepage should degrade gracefully when plan data fails to load.

## Routes That Need More Testing

The local suite confirms these Owner routes open:

```text
/dashboard
/profile
/inventory
/onboarding
/machine-onboarding
/calculator
/production
/attendance
/customers
/sales
/payments
/outstanding
/expenses
/staff
/integrations
/ai-supervisor
```

Routes needing deeper data-entry coverage:

```text
/onboarding
/machine-onboarding
/production
/customers
/sales
/payments
/attendance
/inventory
/staff
/integrations
/ai-supervisor
```

Reason:
Many of these flows depend on prerequisite records, such as workers, machines, stock, customers, or pending dues.

## Recommended Future Test Cases

### Local full-flow expansion

1. Create worker in onboarding.
2. Create machine in onboarding.
3. Add raw material and packaging stock.
4. Add final product stock.
5. Add customer.
6. Create production entry.
7. Create sale.
8. Add payment collection.
9. Verify dashboard numbers update after each step.
10. Verify inventory changes after production and sales.

### Role-based access

1. Owner creates Sub-Owner.
2. Owner creates Supervisor.
3. Owner creates Operator.
4. Login as each role.
5. Verify allowed routes open.
6. Verify forbidden routes redirect or show unauthorized state.

### Subscription gating

1. Trial active with future trial end allows access.
2. Paid active with future expiry allows access.
3. Manual override allows access.
4. Expired subscription blocks dashboard.
5. Staff lock screen appears when factory subscription is expired.

### Production smoke expansion

Only with explicit test credentials:

1. Login.
2. Open dashboard.
3. Open top protected routes.
4. Assert no `404`, `500`, failed requests, or browser console errors.
5. Do not submit forms unless using a dedicated production test tenant.

## Recommended Monitoring and Logging Improvements

### Frontend

- Log API base URL at app startup in non-production only.
- Add a production-safe error boundary for failed API data panels.
- Capture client-side errors with a monitoring tool.
- Add route-level loading and error states that expose useful testable text.

### Backend

- Add structured request logging for `5xx` responses.
- Add correlation/request IDs to API responses.
- Add auth failure logs without exposing secrets.
- Add subscription resolver logs only where safe and avoid sensitive customer data.

### Deployment

- Add a deployment smoke check that fails if production JS contains `localhost:8000`.
- Add CI/CD validation for required frontend env variables.
- Add a simple `/api/health` endpoint alias if the frontend and tests standardize on `/api`.

## How To Recognize Similar Bugs Faster

### Network/config bugs

Signals:
- Request URL points to localhost from production.
- CORS error in console.
- `net::ERR_FAILED` or `net::ERR_ABORTED`.
- Page loads but dynamic data is missing.

Manual investigation:
Open DevTools Network tab, reload page, filter failed requests.

### Selector/test bugs

Signals:
- Playwright strict mode violation.
- Error says a locator resolved to 2 or more elements.
- Failure happens before an API call.

Manual investigation:
Use Playwright's error context or Inspector to see all matching elements.

### Validation bugs

Signals:
- Invalid data submits successfully.
- Required field can be skipped.
- Frontend blocks but backend accepts malformed payload.

Manual investigation:
Test both the browser form and direct API payloads.

### Auth bugs

Signals:
- Protected route opens without token.
- Auth token missing after login.
- Wrong role can open restricted page.
- Expired subscription still allows data reads.

Manual investigation:
Inspect localStorage, request headers, API status codes, and route redirects.
