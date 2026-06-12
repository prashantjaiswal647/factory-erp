# Pilot Factory Simulation Report: 30-Day Operational Run

This simulation run verifies that inventory weights, collections, briefings, and alert flows sync correctly over 30 days of factory operations.

---

### Scenario Ledger & State Verification

#### Day 1: Setup & Opening Stock
* **Action**: Onboarded owner. Entered opening inventory stock:
  - 10,000 Kg Blank Roll.
  - 5,000 Kg Bottom Roll.
* **Balances**: RM Stock = 15,000 Kg. FG Stock = 0 Boxes.

#### Days 2–7: Production Run
* **Action**: Recorded 1,000 boxes made daily. Consumed 800 Kg Blank, 200 Kg Bottom daily.
* **Balances**:
  - Blank Roll: 10,000 - (800 * 6) = 5,200 Kg.
  - Bottom Roll: 5,000 - (200 * 6) = 3,800 Kg.
  - Finished Goods: 6,000 Boxes.

#### Day 8: Sales Billing
* **Action**: Sold 4,000 boxes to "Customer A" at ₹800 per box. Total invoice = ₹32,00,000 (taxable).
* **Balances**:
  - FG Stock = 6,000 - 4,000 = 2,000 Boxes.
  - Customer A Outstanding: ₹32,00,000.

#### Day 10: Partial Payment Received
* **Action**: Customer A pays ₹12,00,000.
* **Balances**:
  - Customer A Outstanding: ₹20,00,000.
  - status: `partial`.

#### Day 15: Outstanding Alert Triggered
* **Action**: Invoice is 7 days past due. Telegram Collection War Room fires:
  - Triggered Alert: `OUTSTANDING_DUE_WARNING` sent to owner.
  - Outstanding: ₹20,00,000.

#### Day 16: Recovery Suggestions Loaded
* **Action**: Collection War Room dashboard shows Customer A in the `8-15 days` aging bucket with suggesting recovery action:
  * "Customer A has Rs 20 Lakhs outstanding. Send Telegram reminder."

#### Day 20: Recovery Reminder Sent
* **Action**: Owner triggers warning. Direct message with outstanding ledger details delivered.

#### Day 25: Collection Received
* **Action**: Received payment of ₹20,00,000. Invoice status shifts to `resolved`.
* **Balances**:
  - Total Outstanding: ₹0.
  - Total Collections: ₹32,00,000.

#### Day 30: Monthly Review
* **Action**: Fetched `/api/briefings/history?days=30`.
* **Verification**:
  - All 30 snapshots exist.
  - Health scores show an upward trend (from 60/100 on Day 15 to 92/100 on Day 30).
  - Cross-factory isolation tests assert zero leakage between databases.
