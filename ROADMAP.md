# Munshi AI Roadmap

This document consolidates the product execution roadmap, monthly milestones, and priority scores.

---

## 1. Product Execution Premise

Munshi AI is a paying ERP serving real Indian factory owners. Every feature is evaluated against one question:
> "Will an Indian paper-cup / glass factory owner open Munshi AI tomorrow morning because of this feature?"

### Prioritization Formula:
```
Priority Score = (Owner Pain * 5) * (Daily Usage * 4) * (Revenue Impact * 5) * (Pilot Adoption * 5) - (Implementation Cx * 2)
```
- **Score < 100,000** -> Defer
- **Score 100K - 1M** -> Could-have
- **Score 1M - 5M** -> Should-have
- **Score > 5M** -> Must-have (next sprint)

---

## 2. Feature Release Phases (P4.5 - P5.1)

| Phase | Title | Pain | Daily | Rev | Adopt | Cx | Raw Score | Tier |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **P4.5** | Telegram Assistant Completion | 9 | 10 | 6 | 9 | 5 | 4,859,990 | Must-have |
| **P4.6** | Invoice Intelligence | 10 | 9 | 8 | 9 | 4 | 3,240,000 | Must-have |
| **P4.7** | Recovery Intelligence | 10 | 8 | 10 | 9 | 5 | 3,600,000 | Must-have |
| **P4.8** | Factory Daily Briefing AI | 9 | 10 | 7 | 9 | 6 | 5,670,000 | Must-have |
| **P4.9** | Machine Breakdown Logging | 8 | 6 | 7 | 7 | 3 | 1,176,000 | Should-have |
| **P5.0** | Operational Intelligence Layer | 7 | 5 | 6 | 5 | 8 | 210,000 | Could-have |
| **P5.1** | Advanced Intelligence (ML models) | 4 | 2 | 3 | 2 | 10 | 48,000 | DEFERRED |

*Note: P5.1 is explicitly blocked until there are 10+ paying factories and 90+ days of historical data per factory.*

---

## 3. Month-by-Month 6-Month execution milestones

### MONTH 1 - Stabilization & Pilot 1 Cutover
- **Objectives:** Complete Bulk Onboarding P0/P1 fixes, cut over the first pilot factory, stand up the payments integration, and begin webhook processing.
- **Risks:** Pilot data containing duplicate entries. Mitigation: Run pre-migration deduplication checks.

### MONTH 2 - Webhooks & AI Supervisor V1 Foundation
- **Objectives:** Complete Payments subscriptions & dunning logic, start AI Supervisor briefings, implement Audit Trail UI, and clean up sidebar absolute URLs.
- **AI Focus:** Daily Morning Briefings via Telegram (Capability 1), Low-Stock alerts (Capability 4), Outstanding aging highlights (Capability 6).

### MONTH 3 - Multi-Tenant Scaling & Production Run
- **Objectives:** Onboard pilot factories 2 & 3, implement Razorpay webhook integrations, build automatic PDF generation pipelines.
- **Infra:** Set up localized backups and daily performance logs.

### MONTH 4 - Machine Downtime & Telemetry OEE Module
- **Objectives:** Roll out OEE charts and shift log exports, integrate machine downtime classifications, enable real-time operator alerts.

### MONTH 5 - Advanced CRM & Collection War Room
- **Objectives:** Upgrade collections module to support custom UPI discount rules, release automatic recovery reminders via WhatsApp/Telegram.

### MONTH 6 - Analytics BI Console
- **Objectives:** Add graphical dashboards mapping Sales vs. Collections, machine efficiency ratios, and waste analytics.

---
**Source Files Compressed:** `MUNSHI_6_MONTH_ROADMAP.md`, `MUNSHI_AI_PRIORITY_ROADMAP.md`
