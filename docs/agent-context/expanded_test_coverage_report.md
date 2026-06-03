# Munshi AI - Expanded Test Coverage Report

This report outlines the successfully expanded test suite designed to validate multi-tenant factory isolation, bulk upload idempotency, salary and attendance calculation, subscription limits, and invoice PDF generation for Munshi AI ERP.

The test suite is located in [test_expanded_erp_flows.py](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/api/tests/test_expanded_erp_flows.py).

---

## 1. Root Cause Analysis & Fixes Applied

As requested, all test failures encountered during validation were analysed and resolved:

### 1.1 NameError in `routers/operations.py` (Daily Production Entry)
* **Symptom:** Creating daily production records failed with HTTP 500 status code.
* **Root Cause:** In `routers/operations.py`, the system was querying `MaterialYield` but did not import the model, raising `NameError: name 'MaterialYield' is not defined`.
* **Resolution:** Added `MaterialYield` to the `from models import ...` list at the top of [operations.py](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/api/routers/operations.py#L27-L30). No business logic was altered.

### 1.2 Global dependency overrides cleanup side effects
* **Symptom:** Tests like `test_subscription_limits_and_trial_expiry` failed when trying to resolve hosts to `ai-erp-postgres`.
* **Root Cause:** Previous test cleanup steps called `main_app.dependency_overrides.clear()`, which deleted the global `get_db` override to SQLite. Subsequent tests then attempted to connect to the production PostgreSQL environment.
* **Resolution:** Replaced `main_app.dependency_overrides.clear()` with targeted popping of temporary session variables (`get_current_user`, `get_current_active_user`, `require_owner`), preserving the SQLite DB override.

### 1.3 Bypass configuration interfering with subscription limit tests
* **Symptom:** Expired trials and inactive subscriptions returned HTTP 200 instead of HTTP 402.
* **Root Cause:** `ENV=development` and `BYPASS_TRIAL=true` in the local `.env` configuration caused the authentication middleware helper `is_trial_bypass_enabled()` to return `True`, bypassing trial limits.
* **Resolution:** Mocked `auth.is_trial_bypass_enabled` to return `False` during trial checks using Pytest's `monkeypatch` utility.

### 1.4 Dashboard summary schema and Outstanding dues field format
* **Symptom:** Key errors on `total_sales_today` and type assertions failing (`'0.00' == 0`).
* **Root Cause:** The endpoint returned `total_sales_last_7_days` and decimal serializations to strings (e.g. `"0.00"`).
* **Resolution:** Aligned the test assertions to check `total_sales_last_7_days` and parsed outstanding totals to `float` for comparison.

---

## 2. Test Execution Summary

All 5 test suites execute and pass successfully on the local SQLite in-memory engine:

```text
tests/test_expanded_erp_flows.py::test_factory_isolation_flow PASSED
tests/test_expanded_erp_flows.py::test_bulk_upload_idempotency PASSED
tests/test_expanded_erp_flows.py::test_salary_attendance_flow PASSED
tests/test_expanded_erp_flows.py::test_subscription_limits_and_trial_expiry PASSED
tests/test_expanded_erp_flows.py::test_invoice_pdf_smoke_and_isolation PASSED
```

---

## 3. Coverage Analysis

The integration test suite coverage report:

| Module | Statements | Missed | Coverage | Key Highlights |
| :--- | :--- | :--- | :--- | :--- |
| **`routers/attendance.py`** | 256 | 111 | **57%** | Auto-marking of workers on production log entry, daily wage calculations. |
| **`services/invoice_pdf.py`** | 212 | 97 | **54%** | PDF generation logic, template layout rendering, and multi-tenant file checks. |
| **`routers/operations.py`** | 473 | 270 | **43%** | Production tracking sequence, raw material consumption. |
| **`routers/dashboard.py`** | 186 | 114 | **39%** | AI-driven insights fallback queries, caching mechanisms. |
| **`routers/payments.py`** | 218 | 134 | **39%** | Payments allocation queues, outstanding collections. |
| **`services/accounting.py`** | 72 | 43 | **40%** | Due allocations, transaction records. |
| **`services/tenant_context.py`** | 9 | 0 | **100%** | Multi-tenant factory isolation context. |
