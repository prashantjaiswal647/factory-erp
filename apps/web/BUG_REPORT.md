# BUG REPORT

This report includes product-impacting bugs and QA harness bugs discovered while building and running the Playwright E2E suite.

## BUG-001: Production frontend calls localhost API

**Bug ID:** BUG-001

**Bug Title:** Production frontend calls localhost API instead of production API

**Route/Page where bug occurred:** `https://munshiai.co.in/`

**Exact UI element involved:** Homepage pricing/plans section loader. The failing request is triggered while the page loads billing plan data.

**Steps to reproduce:**
1. Open a terminal in `apps/web`.
2. Run `npm run test:e2e:prod`.
3. Let the production smoke test open `https://munshiai.co.in/`.
4. Watch the browser network requests captured by Playwright diagnostics.

**Expected behavior:**
The live frontend should call the live API, such as:

```text
https://munshiai.co.in/api/billing/plans
```

The production smoke test should complete without browser console errors, failed network requests, or API `4xx/5xx` responses.

**Actual behavior:**
The live frontend attempts to call:

```text
http://localhost:8000/api/billing/plans
```

From a production browser, `localhost` means the visitor's own machine, not the VPS. The browser blocks the request.

**Root cause analysis:**
The frontend API base URL resolution falls back to `http://localhost:8000`. On production, the deployed build appears to have no production `VITE_API_URL`, or the runtime URL detection does not recognize `munshiai.co.in`. Because of that, production users receive a frontend bundle that still points API calls to local development.

Relevant source area:

```text
apps/web/src/lib/api.ts
```

**Issue category:** Deployment/Configuration issue

**Severity:** High

Production pages that need API data can fail for every user.

**Screenshot path:**

```text
apps/web/test-results/production-smoke-productio-d4f91-without-client-API-failures-chromium-retry1/test-failed-1.png
```

**Playwright trace path:**

```text
apps/web/test-results/production-smoke-productio-d4f91-without-client-API-failures-chromium-retry1/trace.zip
```

**Console errors captured:**

```text
Access to XMLHttpRequest at 'http://localhost:8000/api/billing/plans' from origin 'https://munshiai.co.in' has been blocked by CORS policy: Permission was denied for this request to access the loopback address space.
Failed to load resource: net::ERR_FAILED
```

**Failed network requests captured:**

```text
GET http://localhost:8000/api/billing/plans net::ERR_FAILED
```

**Related API endpoint:**

```text
GET /api/billing/plans
```

**Suggested fix:**
Update production API base URL handling so production builds never fall back to localhost. Prefer explicit `VITE_API_URL=https://munshiai.co.in`, or make `getBaseURL()` use `window.location.origin` for `munshiai.co.in`.

Suggested Codex fix prompt:

```text
Fix production API base URL resolution for the React/Vite frontend.

Problem:
The live site https://munshiai.co.in calls http://localhost:8000/api/billing/plans.

Expected:
Production must call https://munshiai.co.in or the configured VITE_API_URL. Localhost should only be used for local development.

Tasks:
1. Inspect apps/web/src/lib/api.ts and deployment env handling.
2. Update getBaseURL so munshiai.co.in uses same-origin API or VITE_API_URL.
3. Do not change deployment config automatically.
4. Verify with npm run build and npm run test:e2e:prod.
```

**Actual implemented fix if safely fixed:**
Fixed in:

```text
apps/web/src/lib/api.ts
```

The API base URL resolver now follows this rule:

1. Use `VITE_API_URL` if explicitly configured.
2. Use `http://localhost:8000` only when the frontend is running on `localhost` or `127.0.0.1`.
3. Use `window.location.origin` for production domains such as `https://munshiai.co.in`.

Because API calls already include `/api/...`, production requests now resolve to same-origin URLs like:

```text
https://munshiai.co.in/api/billing/plans
```

Verification completed locally:

```text
npm run build
npm run test:e2e:local
```

### Learning Section

**How the bug was discovered:**
The production Playwright smoke test loaded the live homepage and used a diagnostics fixture that listens for failed network requests, console errors, and API `4xx/5xx` responses.

**What signal indicated a problem:**
The test failed because diagnostics captured a failed request to `http://localhost:8000/api/billing/plans`.

**How a QA engineer would investigate it manually:**
1. Open `https://munshiai.co.in/` in Chrome.
2. Open DevTools.
3. Go to the Network tab.
4. Reload the page.
5. Filter for `billing/plans`.
6. Notice that the request points to `localhost:8000`.
7. Open the Console tab and confirm the CORS/loopback error.

**How Playwright detected it:**
The diagnostics fixture subscribed to:

```text
page.on("requestfailed")
page.on("console")
page.on("response")
```

Then the production smoke test called `diagnostics.expectClean()`, which failed because a bad localhost request was captured.

**What files were involved:**

```text
apps/web/src/lib/api.ts
apps/web/e2e/fixtures/diagnostics.ts
apps/web/e2e/tests/production/smoke.spec.ts
```

**What debugging steps were used:**
1. Ran `npm run test:e2e:prod`.
2. Read the failing Playwright output.
3. Checked the diagnostics attachment.
4. Confirmed the exact failed URL and console message.
5. Documented the issue as a deployment/configuration bug.

**How to identify similar bugs in future:**
Look for production network calls to:

```text
localhost
127.0.0.1
0.0.0.0
private IPs
wrong protocol, such as http from https pages
```

Any public site calling these URLs is usually misconfigured.

---

## BUG-002: Signup submit selector matched both tab and form submit button

**Bug ID:** BUG-002

**Bug Title:** Playwright signup test clicked an ambiguous `Sign Up` selector

**Route/Page where bug occurred:** `http://localhost:5173/login?tab=signup`

**Exact UI element involved:** `Sign Up` tab button and `Sign Up` form submit button

**Steps to reproduce:**
1. Run `npm run test:e2e:local`.
2. The signup validation test opens the signup page.
3. The test tries to click `getByRole("button", { name: /^Sign Up$/ })`.

**Expected behavior:**
The test should click the signup form submit button.

**Actual behavior:**
Playwright found two matching buttons:

```text
button "Sign Up" tab
button "Sign Up" form submit
```

Playwright strict mode failed the test because the selector was ambiguous.

**Root cause analysis:**
The test selector was too broad. The UI legitimately has two `Sign Up` buttons visible at the same time: one tab control and one form submit action.

**Issue category:** Frontend test automation bug

**Severity:** Low

This was not a product bug. It was a test harness selector issue.

**Screenshot path:**

```text
apps/web/test-results/local-auth-flow-local-auth-7afe5--storage-and-dashboard-load-chromium/test-failed-1.png
```

**Playwright trace path:**

```text
apps/web/test-results/local-auth-flow-local-auth-7afe5--storage-and-dashboard-load-chromium-retry1/trace.zip
```

**Console errors captured:**

```text
None relevant.
```

**Failed network requests captured:**

```text
None relevant.
```

**Related API endpoint:**

```text
None. Failure happened before API submission.
```

**Suggested fix:**
Scope the selector to the signup form instead of searching the whole page.

**Actual implemented fix if safely fixed:**
Fixed in:

```text
apps/web/e2e/pages/SignupPage.ts
apps/web/e2e/tests/local/auth-flow.spec.ts
```

The submit selector now scopes to the form containing `Full Name`:

```ts
page.locator("form")
  .filter({ has: page.getByLabel("Full Name") })
  .getByRole("button", { name: "Sign Up", exact: true })
```

### Learning Section

**How the bug was discovered:**
The local Playwright suite failed during signup validation.

**What signal indicated a problem:**
Playwright reported a strict mode violation and listed both matching elements.

**How a QA engineer would investigate it manually:**
1. Open the signup page.
2. Observe there is a `Sign Up` tab and a `Sign Up` submit button.
3. Ask which one the test should click.
4. Scope the locator to the form.

**How Playwright detected it:**
Playwright strict mode requires locators to resolve to exactly one element before actions like `click()`.

**What files were involved:**

```text
apps/web/e2e/pages/SignupPage.ts
apps/web/e2e/tests/local/auth-flow.spec.ts
apps/web/src/pages/LoginPage.tsx
```

**What debugging steps were used:**
1. Read the strict mode error.
2. Compared both matched buttons.
3. Scoped the selector to the form.
4. Reran local tests.

**How to identify similar bugs in future:**
Any repeated text such as `Save`, `Add`, `Login`, `Sign Up`, or `Submit` should be scoped to a region, dialog, form, row, or card.

---

## BUG-003: Signup password selector also matched Confirm Password

**Bug ID:** BUG-003

**Bug Title:** Password field selector matched both `Password` and `Confirm Password`

**Route/Page where bug occurred:** `http://localhost:5173/login?tab=signup`

**Exact UI element involved:** `Password` input and `Confirm Password` input

**Steps to reproduce:**
1. Run `npm run test:e2e:local`.
2. The signup page object fills the signup form.
3. The test calls `getByLabel("Password")`.

**Expected behavior:**
Only the `Password` field should be filled.

**Actual behavior:**
Playwright found two fields:

```text
Password
Confirm Password
```

The selector failed in strict mode.

**Root cause analysis:**
`Confirm Password` contains the substring `Password`, so `getByLabel("Password")` without exact matching can match both controls.

**Issue category:** Frontend test automation bug

**Severity:** Low

This was a test selector issue, not an application defect.

**Screenshot path:**

```text
apps/web/test-results/local-protected-routes-loc-d5758-dashboard-opens-after-login-chromium/test-failed-1.png
```

**Playwright trace path:**

```text
apps/web/test-results/local-protected-routes-loc-d5758-dashboard-opens-after-login-chromium-retry1/trace.zip
```

**Console errors captured:**

```text
None relevant.
```

**Failed network requests captured:**

```text
None relevant.
```

**Related API endpoint:**

```text
None. Failure happened while filling the form.
```

**Suggested fix:**
Use exact label matching.

**Actual implemented fix if safely fixed:**
Fixed in:

```text
apps/web/e2e/pages/SignupPage.ts
apps/web/e2e/tests/local/auth-flow.spec.ts
```

The test now uses:

```ts
page.getByLabel("Password", { exact: true })
page.getByLabel("Confirm Password", { exact: true })
```

### Learning Section

**How the bug was discovered:**
The local suite failed while creating a test owner account.

**What signal indicated a problem:**
Playwright strict mode listed two password-related inputs.

**How a QA engineer would investigate it manually:**
1. Inspect the signup form labels.
2. Notice `Confirm Password` includes the word `Password`.
3. Use exact matching or a better form-scoped locator.

**How Playwright detected it:**
The locator did not uniquely identify one input.

**What files were involved:**

```text
apps/web/e2e/pages/SignupPage.ts
apps/web/e2e/tests/local/auth-flow.spec.ts
apps/web/src/pages/LoginPage.tsx
```

**What debugging steps were used:**
1. Read the Playwright strict mode output.
2. Identified substring label overlap.
3. Changed selector to exact matching.
4. Reran local tests.

**How to identify similar bugs in future:**
When a form has labels like `Name` and `Company Name`, or `Password` and `Confirm Password`, prefer exact selectors.

---

## BUG-004: Login submit selector matched both tab and form submit button

**Bug ID:** BUG-004

**Bug Title:** Playwright login test clicked an ambiguous `Login` selector

**Route/Page where bug occurred:** `http://localhost:5173/login`

**Exact UI element involved:** `Login` tab button and `Login` form submit button

**Steps to reproduce:**
1. Run `npm run test:e2e:local`.
2. Let the signup test create a user.
3. The test switches back to login and calls `getByRole("button", { name: /^Login$/ })`.

**Expected behavior:**
The test should click the login form submit button.

**Actual behavior:**
Playwright found two visible `Login` buttons:

```text
Login tab
Login form submit
```

The test failed due to strict mode ambiguity.

**Root cause analysis:**
The test searched the full page for a common button name. The page intentionally uses `Login` for both tab navigation and form submission.

**Issue category:** Frontend test automation bug

**Severity:** Low

This was not a product bug.

**Screenshot path:**

```text
apps/web/test-results/local-auth-flow-local-auth-7afe5--storage-and-dashboard-load-chromium/test-failed-1.png
```

**Playwright trace path:**

```text
apps/web/test-results/local-auth-flow-local-auth-7afe5--storage-and-dashboard-load-chromium-retry1/trace.zip
```

**Console errors captured:**

```text
None relevant.
```

**Failed network requests captured:**

```text
None relevant.
```

**Related API endpoint:**

```text
POST /api/auth/login
```

The failure happened before the endpoint was called.

**Suggested fix:**
Scope login submit clicks to the login form.

**Actual implemented fix if safely fixed:**
Fixed in:

```text
apps/web/e2e/pages/LoginPage.ts
```

The login page object now scopes the action to the form containing `Email or Mobile Number`:

```ts
page.locator("form")
  .filter({ has: page.getByLabel("Email or Mobile Number") })
  .getByRole("button", { name: "Login", exact: true })
```

### Learning Section

**How the bug was discovered:**
The local full-flow suite failed after signup, when it attempted phone-only login.

**What signal indicated a problem:**
Playwright strict mode showed that two `Login` buttons matched.

**How a QA engineer would investigate it manually:**
1. Open `/login`.
2. Observe the `Login` tab and the `Login` submit button.
3. Confirm the intended control is inside the form.
4. Scope the selector to the form.

**How Playwright detected it:**
An action locator resolved to more than one element.

**What files were involved:**

```text
apps/web/e2e/pages/LoginPage.ts
apps/web/src/pages/LoginPage.tsx
```

**What debugging steps were used:**
1. Read Playwright strict mode output.
2. Identified duplicate accessible names.
3. Scoped selector to the login form.
4. Reran local tests.

**How to identify similar bugs in future:**
If a page has tabs and forms using the same labels, selectors must be scoped to the active form or container.
