# QA_EXECUTION_PLAN.md

**Project:** Munshi AI V1.0
**Role:** QA Certification Lead
**Objective:** Systematized verification of production readiness.

## 1. Phase Execution Order
Tests must be executed in this specific sequence to ensure dependencies are met.
1.  **Phase 14 (Migration & Deployment):** Verify the environment is stable.
2.  **Phase 1 (Fresh Factory Validation):** Establish a clean tenant state.
3.  **Phase 13 (Bulk Upload Audit):** Seed the factory with operational data.
4.  **Phase 3 (Tenant Isolation Audit):** Ensure security boundaries before operational tests.
5.  **Phase 11 (Inventory Integrity) $\rightarrow$ Phase 2 (FG Recon):** Verify the core stock engine.
6.  **Phase 10 (Payment/CRM) $\rightarrow$ Phase 6 (Subscription/Billing):** Verify financial flows.
7.  **Phase 7 (RBAC) $\rightarrow$ Phase 8 (Telegram Role):** Verify permission layers.
8.  **Phase 9 (Attendance/Payroll):** Verify secondary operational modules.
9.  **Phase 12 (Dashboard Truth) $\rightarrow$ Phase 5 (Historical Snapshot):** Verify reporting.
10. **Phase 4 (Telegram/Briefing):** Verify external integrations.

## 2. Criticality Mapping

### P0 Tests (Release Blockers)
*Any failure here = Immediate "NO-GO" for release.*
- **Deployment:** MDA-01, MDA-04 (Data loss/Migration failure)
- **Security:** TIA-01, TIA-02 (Cross-tenant data leak)
- **Onboarding:** FFV-01, FFV-02 (Unable to start factory)
- **Core Logic:** IIA-02, IIA-03, FGR-01 (Incorrect stock calculation)
- **Billing:** SBL-02 (Unauthorized access after expiry)
- **RBAC:** RBAC-03, RBAC-05 (Privilege escalation)

### P1 Tests (High Priority)
*Must be resolved before release unless a temporary manual workaround is documented.*
- **Financials:** APA-03 (Wrong salary), PCR-01 (Wrong balance)
- **Integration:** TMB-01 (Bot binding failure)
- **Stability:** BUA-04 (Corrupt import on missing columns)
- **Accuracy:** HSA-01 (Incorrect historical data)

## 3. Test Requirements

### Manual Requirements
- **Fresh Device/Browser:** Clear cookies/cache between Phase 1 and Phase 3.
- **Multiple Accounts:** Minimum 3 distinct accounts (Owner, Sub-Owner, Supervisor) across 2 different factories.
- **Real Excel Files:** Use actual templates provided to customers, not just mock DataFrames.

### Screenshot Requirements
- **UI:** Every "Pass" on a UI-based test must have a screenshot of the final state.
- **Network:** For TIA tests, a screenshot of the Chrome DevTools Network tab showing the 403/404 response.
- **DB:** For FGR and IIA tests, a screenshot of the SQL query result proving the "Truth" calculation.

## 4. Release Criteria
1.  **100% P0 Pass Rate:** No exceptions.
2.  **$\ge$ 90% P1 Pass Rate:** Any remaining P1s must be signed off by the Lead Architect.
3.  **Zero Critical Bugs:** No "Critical" severity bugs open.
4.  **Certification Sign-off:** All 14 phases marked as "Verified".

## 5. Certification Checklist
- [ ] Deployment Environment verified (MDA)
- [ ] Tenant boundaries locked (TIA)
- [ ] Stock Truth verified (FGR/IIA)
- [ ] Billing/Lockout verified (SBL)
- [ ] Role hierarchy enforced (RBAC)
- [ ] Bulk Determinism verified (BUA)
- [ ] Financial Accuracy verified (APA/PCR)
- [ ] Telegram Routing verified (TRA/TMB)
- [ ] Dashboard Truth verified (DTA)
- [ ] Historical Accuracy verified (HSA)
