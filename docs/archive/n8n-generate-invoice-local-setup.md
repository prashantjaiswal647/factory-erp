# Munshi AI Local n8n Invoice Workflow

Import this workflow into local n8n:

`docs/n8n-generate-invoice-workflow.local.json`

## Local URLs

- n8n UI: `http://localhost:5678`
- FastAPI to n8n webhook inside local Docker network: `http://n8n:5678/webhook/generate-invoice`
- Local invoice PDFs written by n8n: `storage/invoices/invoice_<factory_id>_<invoice_id>.pdf`

## Required n8n edits after import

1. Open `Google Sheets - Append Sales Row`.
2. Attach your Google Sheets OAuth credential.
3. Confirm document ID expression is:
   `{{$json.google_spreadsheet_id}}`
4. Confirm sheet name expression is:
   `{{$json.target_sheet_name}}`
5. Create the target tab in Google Sheets before first run, for example:
   `Factory_1_Sales`
6. Activate the workflow.

## Required Docker service

The workflow uses `http://gotenberg:3000/forms/chromium/convert/html` for PDF generation. The local Docker Compose file includes a `gotenberg` service and mounts `./storage/invoices` into n8n as `/files/invoices`.

## FastAPI trigger

React sales invoice submission should call:

`POST /api/sales/invoice`

The existing `/api/sales/add` endpoint remains available and now shares the same async invoice workflow dispatch.

## Owner invoice mode configuration

On the owner Sales Entry page, the owner now chooses one legal invoice mode before saving:

- `Bill of Supply`
- `Tax Invoice`

Only the selected legal branch is printed in the legal invoice section. The same sale can also generate a parallel rough bill for customer-to-customer rate understanding. This rough bill is not a government tax document.

Optional owner inputs:

- `Legal invoice number`: use this when the factory wants to start from a specific invoice number.
- `Rough bill number`: use this when the factory wants a separate informal sequence.
- `Generate parallel rough bill`: keep enabled when the customer-understanding bill should be included.

If invoice numbers are left blank, FastAPI sends the first created sale row ID as the legal invoice number and `RB-<sale_id>` as the rough bill number.

## n8n document branch behavior

The imported workflow reads:

`{{$json.document_policy.legal_invoice_type}}`

FastAPI sends this as:

- `tax_invoice`
- `bill_of_supply`

n8n then creates a PDF with:

1. The selected legal document template.
2. The rough bill template on a separate page when `rough_bill_enabled` is true.

Manual customization point:

Open the node `Build Legal + Rough Bill HTML` and edit:

- Tax Invoice-specific fields such as GSTIN, HSN/SAC, CGST, SGST, IGST.
- Bill of Supply-specific wording.
- Rough bill disclaimer and customer-understanding layout.
