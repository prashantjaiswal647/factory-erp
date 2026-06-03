# Munshi AI - Test Guardian Report

As the **Munshi AI Test Guardian**, I have executed and verified the critical test suite.

---

## 1. Test Verification Results

All **56 tests** in the test suite now pass successfully:

```text
tests/test_e2e_erp_flow.py::test_e2e_erp_workflow PASSED
tests/test_expanded_erp_flows.py::test_factory_isolation_flow PASSED
tests/test_expanded_erp_flows.py::test_bulk_upload_idempotency PASSED
tests/test_expanded_erp_flows.py::test_salary_attendance_flow PASSED
tests/test_expanded_erp_flows.py::test_subscription_limits_and_trial_expiry PASSED
tests/test_expanded_erp_flows.py::test_invoice_pdf_smoke_and_isolation PASSED
tests/test_operations_telemetry_pipeline.py::test_operations_telemetry_pipeline PASSED
...
====================== 56 passed, 726 warnings in 27.30s ======================
```

---

## 2. Issues Identified, Business Impact & Fixes

### 2.1 Test Suite Cross-Pollination (Dependency Overrides Pollution)

* **Failing Tests:** `tests/test_e2e_erp_flow.py::test_e2e_erp_workflow` and `tests/test_operations_telemetry_pipeline.py::test_operations_telemetry_pipeline` when executed concurrently/sequentially in the same process.
* **Business Impact:** High development friction. False failures in the CI/CD pipeline or local tests might delay releases and mask real bugs in critical workflows.
* **Root Cause:**
  1. `test_e2e_erp_flow.py` and `test_operations_telemetry_pipeline.py` defined their own mock database engines and set global overrides (e.g. `main_app.dependency_overrides[get_db] = override_get_db`) at the Python module level (during import time).
  2. When pytest collected and loaded all files, the last imported file overwritten the `get_db` override for all other tests.
  3. Consequently, the app was pointed to a clean/empty database belonging to another test file, causing queries to fail with errors like `OperationalError: no such table: machines`.
  4. At the end of execution, `test_operations_telemetry_pipeline.py` called `main_app.dependency_overrides.clear()`, wiping all overrides for subsequent runs.
* **Minimal Fix:**
  - Scoped the database and user dependency overrides strictly to the test lifecycle by placing them inside a yielding autouse `pytest.fixture` in [test_e2e_erp_flow.py](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/api/tests/test_e2e_erp_flow.py#L66-L77), [test_expanded_erp_flows.py](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/api/tests/test_expanded_erp_flows.py#L66-L79), and [test_operations_telemetry_pipeline.py](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/api/tests/test_operations_telemetry_pipeline.py#L53-L61).
  - Used `.pop(...)` for cleanup instead of `.clear()`.
