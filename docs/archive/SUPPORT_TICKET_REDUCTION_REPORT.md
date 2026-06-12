# Support Ticket Reduction Report: Pilot Verification

This report reviews potential friction points across ERP forms, pages, and workflows to eliminate onboarding and operational support calls.

---

### Issue 1: Raw Material vs Finished Goods Stock Concept Drift
* **Problem**: On the Inventory Page, "Cups (Finished Goods)" and "Blank Rolls / Bottom Rolls (Raw Material)" are edited via similar buttons, but have completely distinct units (Kg vs Boxes/Cups).
* **Confusion**: Owners frequently input Finished Goods in kilograms or Raw Materials in boxes, throwing off data.
* **Suggested Fix**: Force unit suffix rendering inside input forms (e.g., `Enter weight (Kg)` vs `Enter count (Boxes)`). Do not show a generic "Quantity" label.
* **Priority**: HIGH 🔴

---

### Issue 2: Excel Bulk Upload Conflict Errors
* **Problem**: Re-uploading a file with identical rows throws database index violation errors if not handled as a clean upsert.
* **Confusion**: The owner receives a cryptic "Internal Server Error" rather than a clear list of what values conflicted.
* **Suggested Fix**: Convert bulk-upload database constraint failures to user-friendly JSON reports showing Sheet, Row, and conflict details.
* **Priority**: HIGH 🔴

---

### Issue 3: Manual Connect Code Flow Cases
* **Problem**: The 6-digit Telegram connection code is generated in uppercase (e.g., `A5X8T1`), but users frequently type lower-case characters when entering `/start bind_a5x8t1`.
* **Confusion**: Connection fails with "Invalid code" if typed lower-case.
* **Suggested Fix**: Enforce case-insensitive validation for deep links and code entries on the Telegram connection endpoint.
* **Priority**: MEDIUM 🟡

---

### Issue 4: Dashboard Health Score Trend Threshold
* **Problem**: The health score displays a delta (e.g., `+5` or `-10`) comparing today with a 7-day average. The user doesn't know why the score suddenly dropped.
* **Confusion**: "Why did my health score fall to 68 today when I recorded 50,000 cups?" (It could be due to outstanding payment delay).
* **Suggested Fix**: Render a brief tooltip pointing to the lowest scoring component (e.g., *Collections score is 40 due to Rs 2 Lakh overdue billing*).
* **Priority**: MEDIUM 🟡

---

### Issue 5: Missing Invoice Signature Configuration
* **Problem**: If the factory hasn't uploaded a signature template, printing or sending invoices generates an error or prints with a blank placeholder.
* **Confusion**: Owners think the PDF feature is broken.
* **Suggested Fix**: Replace signature error crash with a standard fallback text "Authorized Signatory" inside the PDF layout template.
* **Priority**: LOW 🟢
