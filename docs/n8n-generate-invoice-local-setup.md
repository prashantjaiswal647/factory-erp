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
