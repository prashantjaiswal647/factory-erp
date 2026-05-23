# UX REPORT

Generated from:

```text
npm run test:e2e:ux
```

Result:

```text
14 passed
```

UX-001 is now resolved. The failed expense-save path is covered by Playwright without `test.fail()`.

## UX-001: Expense Save Failure Does Not Show A Visible Error Message

**Area:** Form UX

**Route/Page:** `/expenses`

**Exact UI element:** `Add Expense` button in the `Factory Expenses` form

**Severity:** Medium, resolved

**Screenshot:**

```text
apps/web/test-results/ux-form-ux-UX---forms-expe-b57b3-ors-without-navigating-away-chromium-retry1/test-failed-1.png
```

**Playwright trace:**

```text
apps/web/test-results/ux-form-ux-UX---forms-expe-b57b3-ors-without-navigating-away-chromium-retry1/trace.zip
```

**What happened:**
The UX test forced the `POST /api/expenses` request to return `500` with this payload:

```json
{ "detail": "Forced UX failure" }
```

The page stayed on `Factory Expenses`, but no visible error toast/message appeared for the user.

**Expected UX:**
When expense save fails, the user should see a clear error message near the form, for example:

```text
Forced UX failure
```

or:

```text
Expense save failed. Please try again.
```

**Verified UX:**
The page stays on `Factory Expenses`, renders the backend error message inside the DOM, re-enables the `Add Expense` button, and preserves the user's typed `Expense Name` and `Amount`.

**Console / network signal:**

```text
[api] 500 POST http://localhost:8000/api/expenses
[console] Failed to load resource: the server responded with a status of 500 (Internal Server Error)
```

**Recommendation:**
Keep the user on the form and show an inline error alert directly below the form controls. The alert should explain the failure and tell the user they can retry.

**Suggested UI improvement:**
- Add a red bordered error alert below the `Add Expense` form.
- Preserve the user's typed `Expense Name` and `Amount`.
- Re-enable the `Add Expense` button after the request fails.
- Use copy like:

```text
Expense could not be saved. Please try again.
```

If the backend provides a safe `detail` message, show that message.

**Current implementation status:**
Resolved and verified. A safe error-handling catch renders a visible inline alert in:

```text
apps/web/src/pages/FactoryExpensesPage.tsx
```

The Playwright regression check now runs normally without `test.fail()` in:

```text
apps/web/e2e/tests/ux/form-ux.spec.ts
```

Verification:

```text
PLAYWRIGHT_BASE_URL=http://localhost:5174 npm run test:e2e:ux
14 passed
```

## UX Areas Verified Without Blocking Issues

### Form UX

Verified:
- Signup required fields focus the first missing field.
- Invalid signup phone number shows clear validation.
- Expense required fields show a helpful message.
- Expense submit button changes to `Adding...` and is disabled during request.
- Duplicate expense submission is guarded.
- Successful expense save shows a success toast.

### Navigation UX

Verified:
- Sidebar navigation opens routes after login.
- Active menu item receives highlighted styling.
- Dashboard opens after login.
- Browser back/forward navigation works.
- Protected routes redirect unauthenticated users to login.

### Mobile UX

Viewports tested:

```text
iPhone 14: 390 x 844
Samsung Galaxy S23: 360 x 780
iPad: 768 x 1024
```

Verified:
- No page-level horizontal scroll.
- Mobile navigation button opens the sidebar.
- Sidebar links are usable.
- Expense form fields are usable.
- Inventory table area or empty state is usable.

### Performance UX

Verified:
- Landing page first visible content renders under the test threshold.
- Dashboard loading indicator appears.
- Dashboard renders under the test threshold.
- Empty state appears for a fresh factory expense table.

### Accessibility UX

Verified:
- Keyboard tab navigation reaches visible focused elements.
- Login form labels are discoverable.
- Axe scan found no serious or critical violations on the login page.
- Axe scan found no serious or critical violations on the dashboard.

## Recommended Next UX Tests

1. Add full customer create validation and success feedback tests.
2. Add production entry validation with seeded worker/machine/product data.
3. Add sales flow validation with seeded customer and stock.
4. Add role-specific mobile navigation tests for Supervisor and Operator.
5. Add visual regression screenshots for mobile dashboard, inventory, and forms.
