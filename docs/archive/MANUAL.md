# 📘 MunshiAI: Integrated Features Manual & Testing Guide

This manual serves as a step-by-step testing guide to directly experience, verify, and understand the five recently implemented high-value B2B SaaS ERP roadmap modules across **MunshiAI**.

---

## 📊 Module 1: Live Machine Telemetry & OEE Controller
### What it does:
Enables shop-floor operators and managers to monitor real-time machine speed, toggle active mould cup sizes, track a chronological history of mould changes with timestamps, and log simulated machine stops with precise downtime reasons.

### How to use & test it:
1. Navigate to the **Onboarding Wizard** page from the sidebar.
2. Select the **Machines** tab.
3. In the **Saved Machines** section, locate your list of machines.
4. Click the **📊 Open Telemetry** button under any saved machine to expand the premium simulator widget.
5. **Adjust Uptime Status**: Toggle the *Machine Status* dropdown between **Running** and **Stopped**.
   - If set to **Stopped**, you'll see a red badge, speed drops to 0, and the **OEE score goes to 0%**.
   - If set to **Running**, the badge turns green, speed returns to optimal, and you can adjust the OEE score dynamically.
6. **Adjust Machine Speed**: Drag the *Current Speed slider*. Notice that the **Overall Equipment Effectiveness (OEE) gauge bar** and percentage label update in real-time based on the speed (scaled out of 80 RPM maximum speed).
7. **Simulate Operator Downtime Logs**: With the machine set to **Stopped**, click on any operator simulator buttons: *⚠️ No paper blank*, *⚠️ Mechanical fault*, *⚠️ Maintenance*, or *⚠️ Power failure*.
   - Watch the halt event instantly populate in the **Live Floor Audit Trail** console with real-time system timestamps.
8. **Simulate Mould Size Swaps**: Select a different cup size from the *Active Mould size* dropdown (65ml, 100ml, 150ml, etc.).
   - Watch the active mould metric update and the mould swap history register cleanly in the **Floor Audit Trail** console!

---

## 📈 Module 2: Predictive AI Inventory Forecasting (Stock-Out Prevention)
### What it does:
Intelligently calculates when critical raw material stocks (Paper Blanks in KG and Bottom Rolls in Rolls) will hit zero based on average daily production speeds. Displays a predictive Time-to-Live (TTL) warning and auto-drafts a supplier Purchase Order (PO) with a one-click **"Order via WhatsApp"** launcher to prevent factory shutdowns.

### How to use & test it:
1. Navigate to the main **Dashboard** page.
2. Scroll below the *Finished Goods Stock* table.
3. Locate the new **AI Stock-Out Prevention & Predictive Forecast** section.
4. **Predictive TTL Calculation**: You'll see real-time cards estimating the remaining days for raw cup blanks and bottom roll rolls:
   - **🔴 Critical (Stock-Out Risk)**: Highlighted in red with a pulsing alert if TTL is less than 5 days.
   - **🟡 Moderate Stock**: Highlighted in amber if TTL is between 5 and 10 days.
   - **🟢 Stock Healthy**: Highlighted in green if TTL is more than 10 days.
5. **Supplier PO Auto-Draft**: Under low/critical stock alerts, read the automated draft message prepared specifically for your cup size blanks or bottom rolls.
6. **WhatsApp Procure Launcher**: Click the **💬 Order via WhatsApp** button.
   - It will open WhatsApp with the pre-formatted B2B purchase request draft message ready to send to your supplier in one click!

---

## 💳 Module 3: True B2B Customer Portal, UPI Gateway & Order Dispatch Pipeline
### What it does:
Gives distributors a self-serve checkout interface, including a modern **UPI QR Pay Now secure mock payment gateway overlay** during checkout. Once checked out, it guides the distributor with a highly responsive, modern **Order Dispatch Stepper Timeline** indicating order lifecycle stages.

### How to use & test it:
1. Open your distributor's B2B Store link (using `/store/{storeToken}`).
2. Add products to the cart.
3. Scroll to the bottom and find the new **Select Payment Method** section.
4. Toggle between **Normal Credit** (Pay later) and **UPI / QR Advance**.
   - Note the **2% instant discount** applied and subtracted from the payable total when **UPI / QR Advance** is selected.
5. Click **Proceed to UPI Pay** (or *Place Order*).
6. **UPI Secure Pay Gateway Modal**: An elegant secure pay portal will pop up displaying:
   - Net payable total with discount.
   - Secure mock QR Code.
   - Bank Account details: *HDFC Bank, VPA: cosmicyog@ybl*.
   - UTR / Transaction ID input field.
7. Enter a mock 12-digit UTR transaction reference ID and click **Verify & Complete Order**.
8. **Order Dispatch Tracking Pipeline**: You will be redirected to the storefront success screen displaying:
   - Order confirmation details.
   - QR/UPI payment reference summary.
   - An elegant **Order Dispatch Pipeline stepper** showing:
     * **Order Received** (Green Check - Completed)
     * **Factory Review** (Pulsing Amber Spinner - Active state awaiting owner's final billing action)
     * **Manufacturing Queue** (Gray - Pending)
     * **Dispatched** (Gray - Pending)

---

## 🤖 Module 4: Omnichannel WhatsApp AI Chat Command Simulator
### What it does:
Equips the AI Supervisor web interface with an interactive lateral sidebar showcasing commonly used WhatsApp bot text and voice command templates. This helps managers easily learn natural language bot syntaxes and click presets to instantly simulate messages.

### How to use & test it:
1. Navigate to the **AI Supervisor** page.
2. Locate the new **WhatsApp Bot Simulator** lateral sidebar panel on the right side of the screen.
3. Review the available WhatsApp command presets divided by categories:
   - **📦 Production Entry**: e.g., *Aaj 25 box bane 210ml Printed design me*
   - **👥 Worker Attendance**: e.g., *mark attendance: Sunil present, Ramesh half day...*
   - **💰 Expense & Sales**: e.g., *add expense Rs 3400 for electricity bill payment*
4. **Simulate a Command**: Click any of the preset template buttons.
   - Watch the command instantly auto-populate into the chat supervisor input box.
5. Click **Send** to dispatch the message. Watch the AI supervisor interpret, approve, and automatically update your ERP databases!

---

## 📊 Module 5: Interactive Financial BI & Profitability Analytics
### What it does:
Upgrades the dashboard with interactive visual charts (Bar, Area, and Pie charts using `recharts`) showing Sales vs. cash collection trends, daily operational cost margins (raw materials, wages, power), and machine-wise wastage heatmaps.

### How to use & test it:
1. Navigate to the main **Dashboard** page.
2. Under the primary Metric Cards section, locate the new **Factory Business Intelligence (BI)** console.
3. **Weekly Sales vs. Collections Bar Chart**: Click the **Overview** tab.
   - Observe the interactive dual bar graph rendering sales made vs. cash collections daily with clean hover tooltips.
4. **Daily Operational Margins Pie Chart**: Click the **Costs** tab.
   - Observe the donut/pie chart detailing daily cost shares (Raw materials, Worker wages, Electricity, and Maintenance) with dynamic HSL-harmonious color legends.
5. **Wastage Rate Heatmap / Trend**: Click the **Wastage** tab.
   - Observe the elegant crimson Area Chart illustrating average raw material wastage percentages across all active floor machines.
