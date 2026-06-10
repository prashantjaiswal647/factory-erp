# UX Polish Report: Pilot Factory Operations

Reviewing all core application pages under the **30-second understanding rule**.

---

### 1. Dashboard View
* **Observation**: Contains multiple large graphs showing production vs target, cost variations, and collection trends. On mobile, this causes significant vertical scrolling.
* **Polish Recommendation**: Collapsed large trend lines into small sparkline graphs; focus on the primary KPIs (Today's Production, Total Outstanding, and Health Score).
* **Estimated Friction**: Low (Mobile check passes).

### 2. Collection War Room
* **Observation**: The customer aging list table overflows on screens under 360px wide, clipping customer names.
* **Polish Recommendation**: Implement horizontal scroll bars on the table wrapper class and display truncated customer names with a hover tooltip.
* **Estimated Friction**: Medium (Important for mobile-first collection management).

### 3. Production Entry Page
* **Observation**: Form requires the owner to input machine, raw material size, packaging size, box count, and scrap weight, requiring multiple clicks and select boxes.
* **Polish Recommendation**: Auto-select the last active machine and raw material type by caching user inputs in local state.
* **Estimated Friction**: High (Owners hate repetitive configuration clicks).

### 4. Briefing History Page
* **Observation**: Long historical list of 30 items fills the screen.
* **Polish Recommendation**: Show a summary of the last 7 days metrics prominently as a card at the top, then list the remaining 30 days as a clean table with a "View Details" overlay.
* **Estimated Friction**: Low.
