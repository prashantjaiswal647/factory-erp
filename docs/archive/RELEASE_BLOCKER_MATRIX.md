# RELEASE_BLOCKER_MATRIX.md

**Project:** Munshi AI V1.0
**Purpose:** High-level risk assessment of the certification phases.

| Phase | Risk Classification | Justification | Impact if Failed |
| :--- | :--- | :--- | :--- |
| **PHASE 1: Fresh Factory** | **BLOCKING** | First touchpoint. Failure here prevents any user from using the system. | Complete churn; zero conversion. |
| **PHASE 2: FG Recon** | **BLOCKING** | Core product value is "Production Intelligence". Inaccurate stock is a fatal flaw. | Loss of user trust; operational chaos. |
| **PHASE 3: Tenant Isolation** | **BLOCKING** | Security/Privacy. Leakage of financial/customer data is a legal and business disaster. | Legal liability; total brand collapse. |
| **PHASE 4: Telegram/Briefing** | **MEDIUM RISK** | High value but not "critical path" for basic accounting. | Reduced user engagement. |
| **PHASE 5: Historical Snapshot**| **MEDIUM RISK** | Important for auditing, but live stock is the primary operational need. | Audit gaps for users. |
| **PHASE 6: Subscription/Billing**| **BLOCKING** | Revenue protection. Failure allows unauthorized free access or locks out paid users. | Revenue loss or payment disputes. |
| **PHASE 7: RBAC Audit** | **HIGH RISK** | Prevents unauthorized destructive actions. | Accidental or malicious data deletion. |
| **PHASE 8: Telegram Role** | **LOW RISK** | Convenience and UX for specific roles. | Minor UX friction. |
| **PHASE 9: Attendance/Payroll** | **HIGH RISK** | Direct impact on worker payments. | Labor disputes; payroll errors. |
| **PHASE 10: Payment/CRM** | **HIGH RISK** | Financial accuracy for customer dues. | Revenue leakage; balance errors. |
| **PHASE 11: Inventory Integrity**| **BLOCKING** | The mathematical foundation of the ERP. | Corrupt state; requires manual DB fix. |
| **PHASE 12: Dashboard Truth** | **MEDIUM RISK** | Reporting accuracy. Users rely on this for decisions. | Misinformed business decisions. |
| **PHASE 13: Bulk Upload** | **HIGH RISK** | Onboarding friction. Complex files can crash the system. | High onboarding failure rate. |
| **PHASE 14: Migration/Deploy** | **BLOCKING** | Stability. Failure leads to downtime or data loss during updates. | Service outage; permanent data loss. |
