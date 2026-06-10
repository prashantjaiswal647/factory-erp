# REAL_FACTORY_LIFECYCLE_REPORT.md

Generated: 2026-06-10T07:54:12.275Z

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
[API LOG] 2026-06-10T07:53:53.440Z | GET http://127.0.0.1:8000/api/factory-health/today -> Status: 200
[API LOG] 2026-06-10T07:53:54.066Z | GET http://127.0.0.1:8000/api/factory-health/today -> Status: 200
[API LOG] 2026-06-10T07:53:57.249Z | GET http://localhost:5173/src/api/billing.ts?t=1781076595565 -> Status: 304
[API LOG] 2026-06-10T07:53:57.329Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078037284 -> Status: 200
[API LOG] 2026-06-10T07:53:57.353Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078037283 -> Status: 200
[API LOG] 2026-06-10T07:53:57.354Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078037283 -> Status: 200
[API LOG] 2026-06-10T07:53:57.405Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781078037368 -> Status: 200
[API LOG] 2026-06-10T07:53:57.406Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781078037354 -> Status: 200
[API LOG] 2026-06-10T07:53:57.418Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:53:57.430Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781078037354 -> Status: 200
[API LOG] 2026-06-10T07:53:57.447Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:53:58.317Z | GET http://127.0.0.1:8000/api/customers/search?q=Test+Customer+42 -> Status: 200
[API LOG] 2026-06-10T07:53:59.340Z | POST http://127.0.0.1:8000/api/payments/add -> Status: 201
[API LOG] 2026-06-10T07:53:59.382Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:53:59.413Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781078039355 -> Status: 200
[API LOG] 2026-06-10T07:53:59.421Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:54:05.593Z | GET http://localhost:5173/src/api/billing.ts?t=1781076595565 -> Status: 304
[API LOG] 2026-06-10T07:54:05.675Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078045633 -> Status: 200
[API LOG] 2026-06-10T07:54:05.700Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078045633 -> Status: 200
[API LOG] 2026-06-10T07:54:05.721Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078045633 -> Status: 200
[API LOG] 2026-06-10T07:54:05.774Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781078045734 -> Status: 200
[API LOG] 2026-06-10T07:54:05.782Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:54:05.807Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781078045734 -> Status: 200
[API LOG] 2026-06-10T07:54:05.814Z | GET http://127.0.0.1:8000/api/sales/outstanding -> Status: 200
[API LOG] 2026-06-10T07:54:09.280Z | GET http://localhost:5173/src/api/billing.ts?t=1781076595565 -> Status: 304
[API LOG] 2026-06-10T07:54:09.341Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078049306 -> Status: 200
[API LOG] 2026-06-10T07:54:09.342Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078049305 -> Status: 200
[API LOG] 2026-06-10T07:54:09.356Z | GET http://127.0.0.1:8000/api/billing/status?t=1781078049306 -> Status: 200
[API LOG] 2026-06-10T07:54:09.421Z | GET http://127.0.0.1:8000/api/onboarding/machines -> Status: 200
[API LOG] 2026-06-10T07:54:09.426Z | GET http://127.0.0.1:8000/api/onboarding/workers -> Status: 200
[API LOG] 2026-06-10T07:54:09.428Z | GET http://127.0.0.1:8000/api/integrations/telegram/status -> Status: 200
[API LOG] 2026-06-10T07:54:09.431Z | GET http://127.0.0.1:8000/api/production/alerts -> Status: 200
[API LOG] 2026-06-10T07:54:09.468Z | GET http://127.0.0.1:8000/api/production/alerts -> Status: 200
[API LOG] 2026-06-10T07:54:09.483Z | GET http://127.0.0.1:8000/api/integrations/telegram/status -> Status: 200
[API LOG] 2026-06-10T07:54:09.490Z | GET http://127.0.0.1:8000/api/onboarding/machines -> Status: 200
[API LOG] 2026-06-10T07:54:09.490Z | GET http://127.0.0.1:8000/api/onboarding/workers -> Status: 200
[API LOG] 2026-06-10T07:54:09.507Z | GET http://127.0.0.1:8000/api/inventory/ -> Status: 200
[API LOG] 2026-06-10T07:54:09.557Z | GET http://127.0.0.1:8000/api/sales/pending -> Status: 200
[API LOG] 2026-06-10T07:54:09.597Z | GET http://127.0.0.1:8000/api/dashboard/analytics -> Status: 200
[API LOG] 2026-06-10T07:54:09.674Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781078049365 -> Status: 200
[API LOG] 2026-06-10T07:54:09.719Z | GET http://127.0.0.1:8000/api/inventory/ -> Status: 200
[API LOG] 2026-06-10T07:54:09.721Z | GET http://127.0.0.1:8000/api/v1/users/me/subscription?t=1781078049365 -> Status: 200
[API LOG] 2026-06-10T07:54:09.788Z | GET http://127.0.0.1:8000/api/sales/pending -> Status: 200
[API LOG] 2026-06-10T07:54:09.801Z | GET http://127.0.0.1:8000/api/dashboard/analytics -> Status: 200
[API LOG] 2026-06-10T07:54:10.024Z | GET http://127.0.0.1:8000/api/alerts/top?limit=5 -> Status: 200
[API LOG] 2026-06-10T07:54:10.162Z | GET http://127.0.0.1:8000/api/factory-health/history?days=30 -> Status: 200
[API LOG] 2026-06-10T07:54:10.218Z | GET http://127.0.0.1:8000/api/factory-health/history?days=30 -> Status: 200
[API LOG] 2026-06-10T07:54:10.623Z | GET http://127.0.0.1:8000/api/alerts/top?limit=5 -> Status: 200
[API LOG] 2026-06-10T07:54:10.810Z | GET http://127.0.0.1:8000/api/factory-health/today -> Status: 200
[API LOG] 2026-06-10T07:54:11.453Z | GET http://127.0.0.1:8000/api/factory-health/today -> Status: 200
```

---
Validation completed successfully.
