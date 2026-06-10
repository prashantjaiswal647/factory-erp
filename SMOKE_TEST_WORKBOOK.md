# Smoke Test Workbook: Pilot Factory Validation

This workbook serves as the verification protocol for Pilot Factory runs.

| Step | Smoke Test Case | Scenario / Parameters | Expected Result | Verified Status |
|---|---|---|---|---|
| **1** | Fresh Factory Onboarding | Create factory, owner username/password, verify subscription activation. | Database writes successfully; user gains Owner access. | PASS |
| **2** | Bulk Upload | Upload master sheet with raw materials, products, and suppliers. | Auto-upserts materials/products without crashing on re-runs. | PASS |
| **3** | Inventory Opening Stock | Set opening kilograms (RM) and initial boxes (FG). | Quantities update correctly in logs and database counts. | PASS |
| **4** | Production Entry | Record daily machine runs, raw material consumption, and wastage. | Reduces blank stock / bottom stock; increments finished goods. | PASS |
| **5** | Production Delete | Remove an erroneous entry recorded earlier. | Stock rolls back and is restored dynamically. | PASS |
| **6** | Sales Entry | Input customer sales invoice details (taxable, rate, quantity). | Generates outstanding balances for customer; triggers order lock. | PASS |
| **7** | Invoice PDF | Request PDF generation endpoint. | ReportLab yields a clean server-side generated PDF stream. | PASS |
| **8** | Payment Entry | Input customer payment receipt matching outstanding tracking ID. | Captures payments, reduces balance, updates ledger. | PASS |
| **9** | Partial Payment | Customer makes 50% partial payment on an invoice. | Balance updates to `partial`; outstanding remains active. | PASS |
| **10** | Full Payment | Customer pays remaining balance. | Status shifts to `resolved`; total outstanding declines. | PASS |
| **11** | Collection War Room | Dashboard view outstanding bucket breakdown and top dues. | Aging buckets (0-7d, 8-15d, 16-30d, 31-60d, 60+d) load correctly. | PASS |
| **12** | Recovery Suggestion | System displays recovery actions for overdue accounts. | Displays overdue balance with suggestion text. | PASS |
| **13** | Telegram Reminder | Trigger manual warning delivery via connected chat. | Inline template message delivers to owner binding. | PASS |
| **14** | Morning Briefing | Verify daily aggregation run at 23:58/9:00 AM. | Merge returns yesterday metrics and recovery totals. | PASS |
| **15** | Briefing History | Retrieve last 30 briefings via REST history endpoint. | Returns history with role-appropriate financial masking. | PASS |
| **16** | Owner Telegram Alerts | Check Telegram alerts for Owner (financial-aware). | Full outstanding, collections, and expense data visible. | PASS |
| **17** | Sub Owner Telegram Alerts | Check Telegram alerts for Sub-Owner (operational-only). | Financial metrics are masked (returned as None or hidden). | PASS |
| **18** | Dashboard Health | Overall factory score calculation. | Component scores merge to form composite score out of 100. | PASS |
| **19** | Logout/Login Persistence | Close tab and navigate back; check session token retention. | User remains logged in or is safely returned to login. | PASS |
| **20** | Mobile Responsive Check | View on mobile resolution wrapper classes. | Sidebar collapses; tables scroll horizontally without breaking layout. | PASS |
