# Munshi AI Data Field Gap and Duplicate Audit

Audit date: 2026-06-13  
Scope: Bulk onboarding Excel -> UI -> calculations -> production -> sales -> outstanding -> payments  
Method: Static inspection of the current onboarding workbook generator/parser, SQLAlchemy models, API routes, frontend pages, and existing tests. No application code or database data was changed.

## 1. Executive Summary

The master onboarding workbook currently contains six sheets:

1. `Company Profile`
2. `Workers`
3. `Customers`
4. `Machines`
5. `Raw Materials`
6. `Finished Goods`

`Raw Materials` contains four marker-driven sections: Cup Blank, Bottom Reel, Box Packaging, and PP Plastic. There is no separate Paper sheet and no Suppliers sheet. In the current implementation, "Paper" is represented by `BlankStock`; the generic `RawMaterial`/metrics models are separate compatibility/calculation structures.

### Overall result

| Area | Result | Main reason |
|---|---|---|
| Workbook sheet coverage | PARTIAL PASS | Core factory, customer, worker, machine, stock, and finished-goods data is present; suppliers and several operational source fields are absent. |
| Calculated-field handling | PASS | Stock totals, invoice totals, balances, dashboard metrics, and other derivable values do not need to become Excel inputs. |
| Customer accounting onboarding | FAIL | Opening outstanding date/note and advance date/note are absent. Bulk upload defaults historical debt to today, which corrupts aging meaning. |
| Production material mapping | FAIL | Blank `material_name` is stored as variety, bottom variety is hardcoded to `Plain White`, and blank-to-bottom linkage is inferred incorrectly from cup size. |
| Worker opening attendance | FAIL | One `previous_attendance_details` number is imported as present days for today only; period and payroll components are lost. |
| Finished-goods opening stock | PARTIAL FAIL | Boxes are supported, but opening loose packets are not. |
| Cost calculation inputs | FAIL | Production costing uses factory costing-master values that are not available in the workbook and therefore may remain zero. |
| Same-file/re-upload idempotency | PARTIAL PASS | Most sections implement upsert logic, but natural keys and normalization are inconsistent and can merge legitimate rows or create case variants. |
| Sales/payment lifecycle | PASS WITH RISKS | Invoice creation, live-stock deduction, outstanding source ledger, payment allocation, and owner verification exist; accounting consistency depends on correct opening-source import and SKU identity. |

### Highest-priority gaps

1. Add customer opening outstanding date and note. Historical debt currently receives the upload date, affecting aging, reminders, and Collection War Room risk.
2. Add explicit `variety_design` to Blank and Bottom sections, and explicit `linked_bottom_size_mm` to Blank. Current defaults can make valid production stock impossible to match.
3. Replace worker `previous_attendance_details` with a structured opening-attendance period and components.
4. Add stable external keys for customers, workers, machines, and SKUs. Name-only matching is not sufficient.
5. Add `initial_loose_packets` to Finished Goods.
6. Add costing-master source inputs, preferably in a separate `Costing & Yields` sheet.

## 2. Excel vs System Field Mapping

The table includes owner-entered source fields and important calculated outputs. A calculated field marked `No` under Excel is intentionally not a template gap.

| Module | Field name in system | Used in route/UI/calculation | Available in Excel? | Excel sheet | Excel column | Calculated? | Required? | Impact if missing | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| Factory | `factory_name` | Profile, invoices, dashboard | Yes | Company Profile | `factory_name` | No | Yes | Factory identity/branding missing | Keep |
| Factory | `gstin` | GST invoice validation/PDF | Yes | Company Profile | `gstin` | No | Conditional | Tax invoices cannot be correctly branded/validated | Keep; require when GST invoices are used |
| Factory | `address` | Profile and invoice PDF | Yes | Company Profile | `factory_address` | No | Conditional | Incomplete invoice identity | Keep |
| Factory | invoice prefix/counters | Invoice numbering | Yes | Company Profile | `invoice_prefix`, three start-sequence columns | No | Yes | Wrong/duplicate legal numbering risk | Keep and validate existing counters before overwrite |
| Factory | advance UPI discount | Storefront/customer advance pricing | Yes | Company Profile | `advance_upi_discount` | No | No | Default pricing policy used | Keep |
| Customer | `name` | Search, sales, ledger, outstanding | Yes | Customers | `name` | No | Yes | Customer cannot be created | Keep |
| Customer | `firm_name` | Customer UI/invoice identity | Yes | Customers | `firm_name` | No | No | Business identity incomplete | Keep |
| Customer | phone/contact | Search, payment lookup, reminders | Yes | Customers | `phone_number`, `contact_number` | No | Strongly recommended | Weak identity and duplicate matching | Keep; normalize one canonical phone |
| Customer | `email` | Customer UI and invoice email delivery | No | - | - | No | No | Email delivery requires later manual entry | Add `email` |
| Customer | `place`/`address` | Customer UI, supply/invoice context | Yes | Customers | `place`, `address` | No | No | Incomplete customer/invoice data | Keep |
| Customer | `gst_number` | Tax invoice buyer GSTIN | Yes | Customers | `gst_number` | No | Conditional | Tax invoice may require manual correction | Keep; validate GSTIN format |
| Customer | opening outstanding amount | Opening receivable source ledger | Yes | Customers | `previous_due` | No | No | Historical receivable omitted | Keep |
| Customer | opening outstanding date | Aging, overdue, Collection War Room | No | - | - | No | Required when previous due > 0 | Bulk import treats old debt as created today | Add `opening_outstanding_date` |
| Customer | opening outstanding note/reason | Ledger/audit UI | No | - | - | No | Required when previous due > 0 | Source context is lost | Add `opening_outstanding_note` |
| Customer | advance balance | Sales advance adjustment | Yes | Customers | `advance_balance` | No | No | Advance credit omitted | Keep |
| Customer | advance balance date/note | Customer ledger context | No | - | - | No | Conditional | Historical advance has no date/reason | Add `advance_balance_date`, `advance_balance_note` |
| Customer | current outstanding/total due | Dashboard, sales, payments | No | - | - | Yes | No | None if source bills are correct | Do not add; derive from active `OutstandingBill` rows |
| Worker | `name` | Production, attendance, worker summary | Yes | Workers | `name` | No | Yes | Worker cannot be selected | Keep |
| Worker | phone | Staff UI/identity | Yes | Workers | `mobile_number` | No | No | Same-name matching remains ambiguous | Keep and normalize |
| Worker | daily wages | Payroll and production labor fallback | Yes | Workers | `daily_wages` | No | Yes for payroll | Labor/payroll becomes zero | Keep |
| Worker | duty/shift hours | Attendance/payroll | Yes | Workers | `duty_hours` | No | Yes | Incorrect duty calculations | Keep |
| Worker | `shift_timing`, `shift_type` | Worker/production operational UI | No | - | - | No | No | Shift defaults/manual entry required | Add optional columns |
| Worker opening attendance | period start/end | Opening attendance and payroll history | No | - | - | No | Required when history is supplied | Current import assigns history to today | Add `opening_period_start`, `opening_period_end` |
| Worker opening attendance | present/half/absent/leave days | Attendance settlement | Partial | Workers | `previous_attendance_details` only | No | Conditional | One number is treated only as present days; other states lost | Replace with explicit component columns |
| Worker opening attendance | overtime, advance, deductions, notes | Settlement/payroll | No | - | - | No | Conditional | Opening payroll liabilities are incomplete | Add explicit columns |
| Machine | name | Production selection and dashboard | Yes | Machines | `machine_name` | No | Yes | Machine cannot be selected | Keep |
| Machine | stable machine number/code | UI sorting, identity, duplicate prevention | No | - | - | No | Strongly recommended | Renames and same-name machines are unsafe | Add `machine_number` or `machine_restore_key` |
| Machine | machine type | Machine setup/UI | No | - | - | No | No | Generic type is used | Add optional `machine_type` |
| Machine | speed | Production target/operations | Yes | Machines | `default_operating_speed` | No | Yes | Performance comparison is incomplete | Keep |
| Machine | target output per shift | Dashboard target progress | Yes | Machines | `target_output_per_shift` | No | Yes | Target progress becomes zero | Keep |
| Machine | mould/cup size | Production SKU compatibility | Yes | Machines | `mould_size_ml` | No | Yes | Wrong product-machine mapping | Keep |
| Machine | bottom size | Production bottom-stock lookup | Yes | Machines | `bottom_size_mm` | No | Yes | Bottom consumption cannot match stock | Keep |
| Machine | raw-material mappings | Machine setup/automation | No | - | - | No | Conditional | Import hardcodes Blank + Bottom for every machine | Add only if factories have machine-specific material rules |
| Blank/Paper | cup size | Inventory and production lookup | Yes | Raw Materials / Cup Blank | `size_ml` | No | Yes | Stock cannot match production | Keep |
| Blank/Paper | variety/design | Production exact SKU lookup | No/incorrect | Raw Materials / Cup Blank | `material_name` is currently stored as variety | No | Yes | Sample `Cup Blank` does not match product `Standard/White` | Add explicit `variety_design`; retain `material_name` as description |
| Blank/Paper | weight per bora | Consumption KG and inventory | Yes | Raw Materials / Cup Blank | `kg_per_sack` | No | Yes before production | Production consumption returns configuration error | Keep; rename label to Weight per Bora (KG) |
| Blank/Paper | total boras | Opening inventory | Yes | Raw Materials / Cup Blank | `total_boras_sacks` | No | Yes for opening stock | No usable stock | Keep |
| Blank/Paper | total KG | Inventory display/cost | No | - | - | Yes | No | None | Do not add; calculate boras x KG/bora |
| Blank/Paper | linked bottom size | Material compatibility | No | - | - | No | Yes | Import sets it equal to cup ML, which is dimensionally wrong | Add `linked_bottom_size_mm` |
| Bottom | bottom size | Machine/production lookup | Yes | Raw Materials / Bottom Reel | `bottom_size_mm` | No | Yes | Bottom stock cannot match machine | Keep |
| Bottom | variety/design | Production exact stock lookup | No | - | - | No | Yes | Import hardcodes `Plain White`, causing variant mismatch | Add `variety_design` |
| Bottom | rolls | Inventory deduction | Yes | Raw Materials / Bottom Reel | `total_individual_rolls` | No | Yes | Production cannot consume bottom | Keep |
| Bottom | total weight KG | Consumption/cost basis | Yes | Raw Materials / Bottom Reel | `total_weight_kg` | No | Yes | KG-per-roll cannot be derived | Keep |
| Bottom | weight per roll | Consumption KG | No | - | - | Yes | No | None when rolls and total weight exist | Do not add; calculate total KG / rolls |
| Box | packaging name/type | Production and packaging lookup | Yes | Raw Materials / Box Packaging | `box_type` | No | Yes | Box stock cannot match finished SKU | Keep; require exact cross-sheet match |
| Box | opening quantity | Inventory/production deduction | Yes | Raw Materials / Box Packaging | `box_quantity_pieces` | No | Yes | No packaging stock | Keep |
| Box | price per box | Inventory/cost reference | Yes | Raw Materials / Box Packaging | `price_per_box_rs` | No | No | Packaging cost may fall back to zero elsewhere | Keep |
| Plastic | plastic type/name | Inventory identity | Yes | Raw Materials / PP Plastic | `plastic_size_type` | No | Yes | Plastic stock cannot be identified | Keep |
| Plastic | cup size | SKU mapping | Yes | Raw Materials / PP Plastic | `used_for_cup_size_ml` | No | Yes | Wrong product mapping | Keep |
| Plastic | boras, KG/bora, price/KG | Inventory and value | Yes | Raw Materials / PP Plastic | matching columns | No | Yes for stocked plastic | Missing quantity/value | Keep |
| Finished Goods | product size | Production/sales SKU | Yes | Finished Goods | `product_size_ml` | No | Yes | SKU cannot be created | Keep |
| Finished Goods | variety/design | Production/sales exact SKU | Yes | Finished Goods | `variety_design` | No | Yes | SKU collision/mismatch | Keep |
| Finished Goods | packaging profile name | Production, Box lookup, sales | Yes | Finished Goods | `packaging_size_name` | No | Operationally yes | Blank fallback can silently create a non-matching box name | Make required for ACTUAL rows |
| Finished Goods | pieces per packet | Packet/box conversion | Yes | Finished Goods | `pcs_per_packet` | No | Yes | Quantity conversion wrong | Keep |
| Finished Goods | packets per box | Live stock and sales conversion | Yes | Finished Goods | `packets_per_box` | No | Yes | Live stock and loose packet sale calculations wrong | Keep |
| Finished Goods | opening boxes | Opening live stock | Yes | Finished Goods | `initial_stock_boxes` | No | No | Opening stock omitted | Keep |
| Finished Goods | opening loose packets | Live stock/sales | No | - | - | No | Required when partial boxes exist | Opening physical stock cannot be represented exactly | Add `initial_loose_packets` |
| Finished Goods | current/live stock | Inventory and sales validation | No | - | - | Yes | None if opening, production, and sales events are correct | Do not add |
| Costing | paper price/KG | Production raw-material cost | No | - | - | No | Required for accurate cost | Production paper cost may be zero | Add to `Costing & Yields` sheet |
| Costing | bottom price/KG | Production raw-material cost | No | - | - | No | Required for accurate cost | Production bottom cost may be zero | Add to `Costing & Yields` sheet |
| Costing | labor/electricity cost per box | Production cost engine | No | - | - | No | Required for configured costing | CPC/profit can be understated | Add to `Costing & Yields` sheet |
| Costing | material yield/pieces per KG | BOM fallback | No | - | - | No | Conditional | Automatic material inference is unavailable; explicit usage still works | Optional yield rows, not mandatory when production captures actual usage |
| Supplier | name, phone, address, GST, opening outstanding | Supplier/purchase models and APIs | No | - | - | No | Conditional on purchase module use | Suppliers must be entered later | Add a `Suppliers` sheet when purchase workflow is enabled |
| Sales | boxes/loose sold, rates, tax, transport | Invoice creation UI | No | - | - | Transaction data | No | None during onboarding | Do not add to onboarding |
| Invoice | taxable total, GST, grand total | Invoice/PDF | No | - | - | Yes | None | Do not add |
| Outstanding | invoice balance/status | Outstanding and Collection War Room | No | - | - | Yes | None | Derive from invoice source and allocations |
| Payment | collected amount/mode/date/reference | Payment Collection | No | - | - | Transaction data | No | None during onboarding except historical migration | Do not add to onboarding; use backup/restore for historical transactions |
| Dashboard | counts, totals, alerts, performance | Dashboard | No | - | - | Yes | None | Do not add |

## 3. Missing Non-Calculated Data Points

Only owner-entered fields that are directly used and cannot be safely calculated are listed here.

### Required for correct core flow

| Priority | Sheet/section | Missing field | Why it is required |
|---|---|---|---|
| P0 | Customers | `opening_outstanding_date` | Drives aging, overdue amount, reminders, and Collection War Room. |
| P0 | Customers | `opening_outstanding_note` | Preserves the source/reason for onboarding debt. |
| P0 | Raw Materials / Cup Blank | `variety_design` | Production matches stock by size and variety; `material_name` is not a safe substitute. |
| P0 | Raw Materials / Cup Blank | `linked_bottom_size_mm` | Cup ML cannot be used as bottom MM. |
| P0 | Raw Materials / Bottom Reel | `variety_design` | Current hardcoded `Plain White` can fail exact production matching. |
| P1 | Workers | opening period and attendance/payroll components | Current single value loses period, half/absent/leave, overtime, advances, and deductions. |
| P1 | Machines | `machine_number` or stable restore key | Required for deterministic identity across rename and re-upload. |
| P1 | Finished Goods | `initial_loose_packets` | Required to represent partial-box physical opening stock. |
| P1 | Costing & Yields | paper price/KG, bottom price/KG, labor/box, electricity/box | Current production costing can silently calculate zero cost. |

### Optional or conditional source fields

- Customers: `email`, `advance_balance_date`, `advance_balance_note`.
- Workers: `shift_timing`, `shift_type`, stable `worker_code`.
- Machines: `machine_type`, `raw_materials_mapped`, `can_swap_moulds`.
- Suppliers: name, phone, address, GST number, and opening outstanding when purchase APIs are enabled.
- Material yields: Blank/Bottom pieces per KG only when automatic BOM fallback is desired.

The following are intentionally not missing fields: total blank KG, average bottom KG/roll, finished-goods live balance, customer current outstanding, invoice totals, payment balance, dashboard counts, cost-per-piece outputs, and stock remaining. They are derivable from source rows and transactions.

## 4. Duplicate Risk Areas

| Entity | Current matching behavior | Re-upload result | Risk | Required correction |
|---|---|---|---|---|
| Customers | Case-insensitive customer name | Usually updates | Two legitimate customers with the same name can merge; phone DB uniqueness and name upsert rules disagree | Use `customer_restore_key`; fallback to normalized phone, GSTIN, then name + firm + place |
| Workers | Candidate query uses original-case names; dictionary uses lowercase | Same case updates; case-only variant can insert or conflict | `Raju` and `raju` are not consistently handled; same-name workers merge | Use `worker_code`/restore key; otherwise normalized phone; enforce functional unique index |
| Machines | Case-insensitive lookup by name | Usually updates | Rename creates a new machine; same-name physical machines cannot coexist | Use `machine_number`/restore key as primary upsert key |
| Blank/Paper | Factory + size + lower variety, but `material_name` becomes variety | Updates matching semantic value | Descriptive names and product varieties are conflated | Separate `material_name` from `variety_design`; unique normalized factory + size + variety |
| Bottom | Factory + size + hardcoded `Plain White` | Updates one row per size | Multiple variants cannot be represented and production may look for another variety | Add variety and key by factory + size + normalized variety |
| Box | Factory + normalized packaging name | Updates | Low risk, but spelling changes create a second row | Add stable packaging/SKU key and cross-sheet validation |
| Plastic | Factory + normalized plastic name + cup size | Updates | Low/moderate risk from spelling changes | Add optional stable material key |
| Finished Goods | Packaging profile is looked up by profile name only; final stock uses profile ID | Usually updates | Same profile name across different size/variety can overwrite/collapse configuration | Key profile and stock by factory + size + variety + normalized packaging name |
| Generic raw material vs stock tables | Parallel `RawMaterial`, metrics, and specialized stock models exist | Depends on route | Dashboard/inventory may display or calculate from different representations | Define one canonical write model and compatibility-only projections |
| Finished stock models | `FinalProductStock` and `FinishedGoodsStock` are synchronized | Depends on sync success | Partial sync failure can cause duplicate/conflicting visible quantities | Treat event-based live SKU calculation as canonical; test both caches after import |

### Database normalization finding

Most database unique constraints are case-sensitive strings, while API upserts use a mixture of exact, trimmed-lowercase, and original-case comparisons. Application-only normalization is therefore insufficient. Add normalized key columns or PostgreSQL functional unique indexes after a data-cleanup migration.

### Existing positive controls

- Only `row_type=ACTUAL` rows are imported.
- Same-workbook duplicate keys are reported and reduced deterministically.
- Tenant IDs come from the authenticated user, not spreadsheet data.
- Tests already cover same-file re-upload for several sections.

These controls do not solve weak natural keys or cross-table SKU collisions.

## 5. Exact Excel Template Changes Needed

### Customers

Add:

```text
customer_restore_key
email
opening_outstanding_date
opening_outstanding_note
advance_balance_date
advance_balance_note
```

Rules:

- `opening_outstanding_date` and `opening_outstanding_note` are required when `previous_due > 0`.
- Opening outstanding must create/update the opening source bill, not a sales invoice.
- A customer cannot have both positive opening outstanding and positive advance balance.

### Workers

Replace `previous_attendance_details` with:

```text
worker_restore_key
opening_period_start
opening_period_end
opening_present_days
opening_half_days
opening_absent_days
opening_paid_leave_days
opening_overtime_hours
opening_advance_paid
opening_deductions
opening_notes
shift_timing
shift_type
```

### Machines

Add:

```text
machine_restore_key
machine_number
machine_type
raw_materials_mapped
```

`machine_number` should be unique per factory when supplied.

### Raw Materials / Cup Blank

Change/add:

```text
material_restore_key
material_name
variety_design
size_ml
linked_bottom_size_mm
weight_per_bora_kg
total_boras_sacks
paper_price_per_kg
```

Keep backward header alias `kg_per_sack -> weight_per_bora_kg`.

### Raw Materials / Bottom Reel

Add:

```text
material_restore_key
variety_design
bottom_price_per_kg
```

Keep rolls and total weight; KG/roll remains calculated.

### Box and Plastic

Add optional `material_restore_key`. Enforce:

- Box `box_type` must match a Finished Goods `packaging_size_name`.
- Plastic cup size must match an existing product size.

### Finished Goods

Add:

```text
product_restore_key
initial_loose_packets
```

Make `packaging_size_name` required for ACTUAL rows. Validate uniqueness using normalized `(product_size_ml, variety_design, packaging_size_name)`.

### New Costing & Yields sheet

Factory-level row:

```text
row_type
paper_price_per_kg
bottom_roll_price_per_kg
polybag_price
carton_price
labour_cost_per_box
electricity_cost_per_box
```

Optional yield rows:

```text
row_type
material_type
size_ml
gsm
pieces_per_kg
```

### New Suppliers sheet

Add only when the purchase/supplier workflow is exposed:

```text
row_type
supplier_restore_key
supplier_name
phone_number
address
gst_number
opening_outstanding
```

## 6. Backend Fixes Needed

1. Introduce factory-scoped stable restore keys and deterministic upsert services for every sheet.
2. Normalize strings with trim + casefold before matching and enforce equivalent database uniqueness.
3. Change customer upsert so changing `previous_due` updates the existing opening outstanding source bill consistently. Do not update only customer balance cache fields.
4. Import opening outstanding date/note into both customer metadata and `OutstandingBill`.
5. Import structured worker opening attendance instead of mapping one number to today's present days.
6. Separate Blank material description from product variety. Stop assigning cup ML to `linked_bottom_size_mm`.
7. Remove hardcoded Bottom variety and require/import the actual variant.
8. Key `PackagingProfile` by full SKU identity, not profile name alone.
9. Import opening loose packets and verify packet-to-box normalization.
10. Add cross-sheet validation before writes: machine bottom size exists, Blank/Bottom variants match Finished Goods, and Box packaging names match Finished Goods.
11. Apply the workbook as one transaction or define explicit atomic section behavior. Current multi-stage compatibility synchronization can partially succeed.
12. Produce structured issues containing sheet, section, row, column, value, and correction.
13. Keep `factory_id` server-owned for all writes.

## 7. Frontend Fixes Needed

1. Update the template instructions and Bulk Upload preview to explain stable keys and conditional required columns.
2. Render structured validation issues by sheet/section/row/column, including cross-sheet mismatches.
3. Show import action per row: `created`, `updated`, `unchanged`, `skipped`, or `error`.
4. Warn before an upload changes opening outstanding, worker opening payroll data, or opening stock.
5. On Inventory and Production, display the same canonical SKU identity: size + variety + packaging.
6. Show opening boxes and loose packets separately.
7. Prevent selection of a production SKU until its Blank variety, Bottom size/variety, Box packaging, and weight-per-bora mappings are valid.
8. Add a post-import reconciliation panel for counts and balances instead of relying only on upload success.

## 8. End-to-End Test Plan

### A. Bulk upload and idempotency

1. Upload a complete workbook into an empty factory.
2. Assert exact counts for customers, workers, machines, each stock bucket, packaging profiles, and finished SKUs.
3. Upload the identical file again.
4. Assert no new rows, no integrity error, and all rows reported `unchanged`.
5. Re-upload with changed values under the same restore keys.
6. Assert rows update in place and historical transaction rows are not duplicated.
7. Test case/space variants and two legitimate same-name customers/workers.
8. Assert another factory can import identical keys without cross-tenant access.

### B. Dashboard and inventory

1. Compare dashboard counts to canonical table counts for the same factory.
2. Verify Blank total KG = boras x weight-per-bora.
3. Verify Bottom KG/roll is derived from total weight and rolls.
4. Verify each finished SKU shows opening boxes and loose packets exactly once.

### C. Production

1. Create production using an imported worker, machine, Blank, Bottom, Box, and Finished Goods SKU.
2. Assert Blank boras/KG, Bottom rolls/KG, and Box stock deductions.
3. Assert finished live stock increases for the exact size/variety/packaging SKU.
4. Assert insufficient stock rolls back every inventory change.
5. Assert cost inputs produce non-zero expected raw-material/labor/electricity cost.

### D. Sales and invoice

1. Create an invoice from the imported finished SKU.
2. Assert available live stock is checked before invoice persistence.
3. Assert sold boxes/loose packets reduce the exact live SKU once.
4. Assert invoice document and line items remain available after payment.
5. Assert invoice source creates one `OutstandingBill` and does not alter opening outstanding.

### E. Payments and bill clear

1. Give a customer opening outstanding plus an invoice outstanding.
2. Record partial payment and assert allocation order: opening outstanding, oldest invoice, manual adjustment, then newer sources.
3. Assert `Payment`, `PaymentCollection`, and `BillPayment` history agrees.
4. Record exact final payment and assert balance becomes zero.
5. Assert the item remains in Collection War Room as "Paid - Awaiting Owner Confirmation".
6. Owner confirms paid; assert it disappears from pending war-room items.
7. Assert invoice and payment history remain available.
8. Assert no stock changes occur for opening outstanding, manual adjustments, or payments.

### F. Regression commands

```powershell
cd apps/api
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q tests/test_onboarding_bulk.py tests/test_sales*.py tests/test_payments*.py

cd ../web
npm run build
npx vitest run
```

Test filenames should be adjusted to the actual suite names when implementing fixes.

## 9. High Risk Accounting/Stock Issues

1. **Opening outstanding aging distortion:** bulk onboarding creates an opening bill with today's date when no source date exists. Old debt appears new and changes overdue/risk decisions.
2. **Opening balance update inconsistency:** customer cached fields can be updated on re-upload while an existing opening `OutstandingBill` is left at its old amount.
3. **Blank variety semantic mismatch:** `material_name` is used as `BlankStock.variety`; template sample data does not necessarily match Finished Goods variety.
4. **Bottom variety hardcoding:** all imported Bottom stock becomes `Plain White`, while production may request `Standard/White` or another design.
5. **Invalid blank-bottom dimensional mapping:** blank import can set `linked_bottom_size_mm` equal to cup `size_ml`.
6. **Packaging profile collision:** profile-name-only lookup can combine different cup sizes/varieties that share a packaging label.
7. **Dual stock representations:** `FinalProductStock`, `FinishedGoodsStock`, generic Inventory, and dynamic event calculations can disagree after partial synchronization.
8. **Zero production cost:** absent costing-master inputs allow valid production quantities with understated or zero cost.
9. **Worker payroll history loss:** the workbook's single prior-attendance value does not preserve the period, attendance states, overtime, advances, or deductions.
10. **Name-based identity:** customer, worker, supplier, and machine records can be merged incorrectly or duplicated after spelling/case changes.
11. **Collection War Room semantics:** fully paid bills remain pending until owner confirmation by design. Tests and UI must distinguish accounting balance zero from owner verification complete.
12. **Invoice persistence requirement:** payment/verification must never delete the invoice. Only an explicit invoice-mistake reversal may reverse stock, and it must preserve an audit trail.

## Audit Source Map

Primary files inspected:

- `apps/api/routers/onboarding.py`
- `apps/api/models.py`
- `apps/api/schemas.py`
- `apps/api/routers/inventory.py`
- `apps/api/routers/operations.py`
- `apps/api/routers/sales.py`
- `apps/api/routers/payments.py`
- `apps/api/routers/dashboard.py`
- `apps/api/services/accounting.py`
- `apps/web/src/components/BulkUploadSection.tsx`
- `apps/web/src/pages/DashboardPage.tsx`
- `apps/web/src/pages/InventoryPage.tsx`
- `apps/web/src/pages/ProductionPage.tsx`
- `apps/web/src/pages/SalesEntryPage.tsx`
- `apps/web/src/pages/CustomersPage.tsx`
- `apps/web/src/pages/OutstandingPage.tsx`
- `apps/web/src/pages/PaymentCollectionPage.tsx`
- `apps/web/src/pages/InvoicesPage.tsx`
- `apps/web/src/pages/CollectionWarRoomPage.tsx`

