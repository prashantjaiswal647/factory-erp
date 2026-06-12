# Munshi AI Testing Guide and QA Workbook

This document consolidates all manual test guides, QA execution plans, workbook checklists, and pilot validation protocols.

---

## 1. QA Execution Plan & Phase Sequence
To ensure all dependencies are met, tests must be run in this sequence:
1. **Migration & Deployment (Phase 14):** Verify environment is stable.
2. **Fresh Factory Validation (Phase 1):** Establish a clean tenant state.
3. **Bulk Onboarding (Phase 13):** Seed the factory with operational master data.
4. **Tenant Isolation Audit (Phase 3):** Validate security boundaries before executing transactions.
5. **Inventory Integrity (Phase 11) & FG Reconciliation (Phase 2):** Verify stock engines.
6. **Payment/CRM (Phase 10) & Subscription/Billing (Phase 6):** Verify financial lifecycles.
7. **RBAC (Phase 7) & Telegram Role Routing (Phase 8):** Verify permission levels.
8. **Attendance & Payroll (Phase 9):** Validate secondary operational modules.
9. **Dashboard & Historical Snapshots (Phase 12 & 5):** Check reporting calculations.
10. **Telegram Integration & Briefing Engine (Phase 4):** Verify external pushes.

### Test Requirements:
- **Clean Environment:** Clear cookies/cache between factory validations and isolation checks.
- **Multiple Role Representation:** Test with at least 3 distinct accounts (Owner, Sub-Owner, Supervisor) across 2 different factories.
- **Real Templates:** Use actual Excel templates for Bulk Onboarding validation, not just synthetic dataframes.

### Release Gate Criteria:
- **100% P0 (Release Blocker) Pass Rate:** No exceptions allowed.
- **>= 90% P1 (High Priority) Pass Rate:** Requires lead architect sign-off.
- **Zero Critical Bugs:** No open issues marked with critical severity.

---

## 2. Pilot Factory Smoke Test Workbook

Use the following protocol for validating pilot factory builds:

| Step | Smoke Test Case | Scenario / Parameters | Expected Result |
| :--- | :--- | :--- | :--- |
| **1** | Fresh Factory Onboarding | Create factory, owner username/password, verify subscription activation. | Database writes successfully; user gains Owner access. |
| **2** | Bulk Upload | Upload master sheet with raw materials, products, and suppliers. | Auto-upserts materials/products without crashing on re-runs. |
| **3** | Inventory Opening Stock | Set opening kilograms (RM) and initial boxes (FG). | Quantities update correctly in logs and database counts. |
| **4** | Production Entry | Record daily machine runs, raw material consumption, and wastage. | Reduces blank stock / bottom stock; increments finished goods. |
| **5** | Production Delete | Remove an erroneous entry recorded earlier. | Stock rolls back and is restored dynamically. |
| **6** | Sales Entry | Input customer sales invoice details (taxable, rate, quantity). | Generates outstanding balances for customer; triggers order lock. |
| **7** | Invoice PDF | Request PDF generation endpoint. | ReportLab yields a clean server-side generated PDF stream. |
| **8** | Payment Entry | Input customer payment receipt matching outstanding tracking ID. | Captures payments, reduces balance, updates ledger. |
| **9** | Partial Payment | Customer makes 50% partial payment on an invoice. | Balance updates to `partial`; outstanding remains active. |
| **10** | Full Payment | Customer pays remaining balance. | Status shifts to `resolved`; total outstanding declines. |
| **11** | Collection War Room | Dashboard view outstanding bucket breakdown and top dues. | Aging buckets (0-7d, 8-15d, 16-30d, 31-60d, 60+d) load correctly. |
| **12** | Recovery Suggestion | System displays recovery actions for overdue accounts. | Displays overdue balance with suggestion text. |
| **13** | Telegram Reminder | Trigger manual warning delivery via connected chat. | Inline template message delivers to owner binding. |
| **14** | Morning Briefing | Verify daily aggregation run at 23:58/9:00 AM. | Merge returns yesterday metrics and recovery totals. |
| **15** | Briefing History | Retrieve last 30 briefings via REST history endpoint. | Returns history with role-appropriate financial masking. |
| **16** | Owner Telegram Alerts | Check Telegram alerts for Owner (financial-aware). | Full outstanding, collections, and expense data visible. |
| **17** | Sub Owner Telegram Alerts | Check Telegram alerts for Sub-Owner (operational-only). | Financial metrics are masked (returned as None or hidden). |
| **18** | Dashboard Health | Overall factory score calculation. | Component scores merge to form composite score out of 100. |
| **19** | Logout/Login Persistence | Close tab and navigate back; check session token retention. | User remains logged in or is safely returned to login. |
| **20** | Mobile Responsive Check | View on mobile resolution wrapper classes. | Sidebar collapses; tables scroll horizontally without breaking layout. |

---

## 3. Features Walkthrough Guide (Manual Test)

### 📊 Module 1: Live Machine Telemetry & OEE Controller
1. Navigate to the **Onboarding Wizard** -> **Machines** tab.
2. Under **Saved Machines**, click the **Open Telemetry** button for any machine.
3. Toggle status between **Running** and **Stopped** (Stopped drops OEE to 0%).
4. Adjust current speed slider (RPM) and watch the OEE gauge update.
5. Click Operator Simulator halt reasons (*No paper blank*, *Mechanical fault*, etc.) to write events directly to the floor audit trail.
6. Swap active mould sizes to register changes in the floor audit trail.

### 📈 Module 2: Predictive AI Inventory Forecasting
1. Go to the main **Dashboard**.
2. Locate **AI Stock-Out Prevention & Predictive Forecast**.
3. View the predictive Time-to-Live (TTL) cards (Red: <5d, Amber: 5-10d, Green: >10d).
4. Click **Order via WhatsApp** to draft and auto-launch purchase orders to your supplier.

### 💳 Module 3: True B2B Customer Portal & UPI Gateway
1. Open distributor store link via `/store/{storeToken}`.
2. Add products and go to payment methods.
3. Select **UPI / QR Advance** (auto-applies 2% discount).
4. Proceed to UPI Pay, enter a mock 12-digit UTR, and complete order.
5. Review the **Order Dispatch Stepper Timeline** indicating lifecycle status.

### 🤖 Module 4: Omnichannel WhatsApp AI Simulator
1. Navigate to the **AI Supervisor** page.
2. In the right panel, choose a command preset under *Production*, *Attendance*, or *Expenses*.
3. Click the preset to populate the text box and press **Send** to simulate natural language processing.

### 📊 Module 5: Financial BI Dashboard
1. Open the main **Dashboard** -> **Factory Business Intelligence (BI)**.
2. View **Overview** (Sales vs. Collections trend bar graph), **Costs** (Operational margins pie chart), and **Wastage** (Machine wastage area chart).

---

## 4. Synthetic Smoke Test E2E Reference
The `synthetic_smoke` script validates an 11-step operational loop from signup to final checkout payment validation.
- **Client Diagnostics Check:** Ensures `diagnostics.expectClean()` is asserted.
- **Logs generated:** `api-responses-log.json` and `console-errors.json`.
- **Verify:** Checks that Sub-Owner roles mask financial numbers correctly into "Masked" strings on the UI.

---
**Source Files Compressed:** `MANUAL.md`, `QA_EXECUTION_PLAN.md`, `SMOKE_TEST_WORKBOOK.md`, `PILOT_SYNTHETIC_SMOKE_REPORT.md`
