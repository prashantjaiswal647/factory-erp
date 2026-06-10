# REAL_FACTORY_LIFECYCLE_REPORT.md

Generated: 2026-06-10T07:31:59.281Z

## Validation Summary

All checks run against the live PostgreSQL database and actual API server. No mock routes used.

- **Status**: PASSED ✅
- **Total Passed Checks**: 24
- **Total Failed Checks**: 0

### Passed Checks
- Step 0: User authenticated and dashboard loaded.
- Step 0 DB: Owner user exists in the database.
- Step 1: Worker "Test Worker 42" created via onboarding UI.
- Step 1 DB: Worker successfully written to the database.
- Step 2: Raw material and product stock registered successfully.
- Step 2 DB: Opening stock records verified in the database.
- Step 2B: Machine registered with mapped raw materials.
- Step 3: Daily production logged successfully.
- Step 3 DB: Production entry database record confirmed.
- Step 4: Sale recorded with Test Customer 42.
- Step 4 DB: Sales invoice recorded in database (₹400).
- Step 5: Branded invoice PDF generated.
- Step 5 DB: Invoice document blob metadata verified in DB.
- Step 6 & 7: Outstanding shows ₹250.
- Step 6 & 7 DB: Outstanding bill balance matched database.
- Step 8: Recovery nudge suggestion copied.
- Step 8 DB: Recovery records active (0 records).
- Step 9: Daily briefing snapshot generated and rendered.
- Step 9 DB: Daily briefing snapshot stored successfully in database.
- Step 10: Full remaining payment of ₹250 recorded.
- Step 10 DB: Payment count matches 2 in the database.
- Step 11: Outstanding resolved to ₹0.
- Step 11 DB: Outstanding bill resolved to ₹0.00 in the database.
- Step 12: Dashboard loaded, showing updated health score.

### Failed Checks
None

## API Logs Captured During Validation
```text
[API LOG] 2026-06-10T07:31:44.688Z | GET http://localhost:5173/src/api/billing.ts?t=1781076595565 -> Status: 304
[API LOG] 2026-06-10T07:31:44.789Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076704749 -> Status: 200
[API LOG] 2026-06-10T07:31:44.814Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076704749 -> Status: 200
[API LOG] 2026-06-10T07:31:44.853Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076704749 -> Status: 200
[API LOG] 2026-06-10T07:31:44.906Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076704847 -> Status: 200
[API LOG] 2026-06-10T07:31:44.908Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:31:44.935Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076704863 -> Status: 200
[API LOG] 2026-06-10T07:31:44.948Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076704847 -> Status: 200
[API LOG] 2026-06-10T07:31:44.952Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:31:45.813Z | GET http://127.0.0.1:8000/api/customers/search?q=Test+Customer+42 -> Status: 200
[API LOG] 2026-06-10T07:31:46.751Z | POST http://127.0.0.1:8000/api/payments/add -> Status: 201
[API LOG] 2026-06-10T07:31:46.789Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:31:46.823Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076706764 -> Status: 200
[API LOG] 2026-06-10T07:31:46.835Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:31:51.808Z | GET http://localhost:5173/src/api/billing.ts?t=1781076595565 -> Status: 304
[API LOG] 2026-06-10T07:31:51.908Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076711848 -> Status: 200
[API LOG] 2026-06-10T07:31:51.914Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076711849 -> Status: 200
[API LOG] 2026-06-10T07:31:51.975Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076711849 -> Status: 200
[API LOG] 2026-06-10T07:31:52.011Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076711932 -> Status: 200
[API LOG] 2026-06-10T07:31:52.032Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076711984 -> Status: 200
[API LOG] 2026-06-10T07:31:52.051Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076711932 -> Status: 200
[API LOG] 2026-06-10T07:31:52.076Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:31:52.104Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:31:56.349Z | GET http://localhost:5173/src/api/billing.ts?t=1781076595565 -> Status: 304
[API LOG] 2026-06-10T07:31:56.444Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076716387 -> Status: 200
[API LOG] 2026-06-10T07:31:56.515Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076716387 -> Status: 200
[API LOG] 2026-06-10T07:31:56.551Z | GET http://127.0.0.1:8000/api/production/alerts -> Status: 200
[API LOG] 2026-06-10T07:31:56.564Z | GET http://127.0.0.1:8000/api/onboarding/machines -> Status: 200
[API LOG] 2026-06-10T07:31:56.564Z | GET http://127.0.0.1:8000/api/integrations/telegram/status -> Status: 200
[API LOG] 2026-06-10T07:31:56.588Z | GET http://127.0.0.1:8000/api/onboarding/workers -> Status: 200
[API LOG] 2026-06-10T07:31:56.631Z | GET http://127.0.0.1:8000/api/billing/status?t=1781076716387 -> Status: 200
[API LOG] 2026-06-10T07:31:56.645Z | GET http://127.0.0.1:8000/api/inventory/ -> Status: 200
[API LOG] 2026-06-10T07:31:56.645Z | GET http://127.0.0.1:8000/api/onboarding/machines -> Status: 200
[API LOG] 2026-06-10T07:31:56.649Z | GET http://127.0.0.1:8000/api/production/alerts -> Status: 200
[API LOG] 2026-06-10T07:31:56.684Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076716461 -> Status: 200
[API LOG] 2026-06-10T07:31:56.704Z | GET http://127.0.0.1:8000/api/onboarding/workers -> Status: 200
[API LOG] 2026-06-10T07:31:56.722Z | GET http://127.0.0.1:8000/api/sales/pending -> Status: 200
[API LOG] 2026-06-10T07:31:56.792Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076716640 -> Status: 200
[API LOG] 2026-06-10T07:31:56.795Z | GET http://127.0.0.1:8000/api/inventory/ -> Status: 200
[API LOG] 2026-06-10T07:31:56.804Z | GET http://127.0.0.1:8000/api/dashboard/analytics -> Status: 200
[API LOG] 2026-06-10T07:31:56.807Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781076716461 -> Status: 200
[API LOG] 2026-06-10T07:31:56.844Z | GET http://127.0.0.1:8000/api/sales/pending -> Status: 200
[API LOG] 2026-06-10T07:31:56.867Z | GET http://127.0.0.1:8000/api/dashboard/analytics -> Status: 200
[API LOG] 2026-06-10T07:31:57.253Z | GET http://127.0.0.1:8000/api/alerts/top?limit=5 -> Status: 200
[API LOG] 2026-06-10T07:31:57.362Z | GET http://127.0.0.1:8000/api/factory-health/history?days=30 -> Status: 200
[API LOG] 2026-06-10T07:31:57.405Z | GET http://127.0.0.1:8000/api/integrations/telegram/status -> Status: 200
[API LOG] 2026-06-10T07:31:57.448Z | GET http://127.0.0.1:8000/api/factory-health/history?days=30 -> Status: 200
[API LOG] 2026-06-10T07:31:57.685Z | GET http://127.0.0.1:8000/api/alerts/top?limit=5 -> Status: 200
[API LOG] 2026-06-10T07:31:57.945Z | GET http://127.0.0.1:8000/api/factory-health/today -> Status: 200
[API LOG] 2026-06-10T07:31:58.506Z | GET http://127.0.0.1:8000/api/factory-health/today -> Status: 200
```

---
Validation completed successfully.
