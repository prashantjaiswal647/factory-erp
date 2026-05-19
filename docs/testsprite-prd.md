# AI ERP System TestSprite PRD

## Product Summary

AI ERP System is a factory operations web application for managing a disposable cup manufacturing business. It includes a React/Vite frontend and FastAPI backend. The app supports authenticated staff workflows, factory setup, inventory, production, sales, customer balances, payment collection, expenses, attendance, billing, and an AI supervisor.

## Test Targets

- Frontend: `http://187.127.165.219:5173`
- Backend: `http://187.127.165.219:8000`
- OpenAPI spec: `http://187.127.165.219:8000/openapi.json`

## User Roles

- Owner: full access to dashboard, staff, inventory, production, attendance, sales, customers, outstanding balances, payments, expenses, onboarding, calculator, billing, profile, and AI supervisor.
- Sub-Owner: broad operational access except owner-only staff administration.
- Supervisor: operational access to inventory, production, attendance, sales, payments, expenses, and AI supervisor.
- Operator: limited access to inventory, production, expenses, and AI supervisor.

## Critical Frontend Flows

- Public landing page loads at `/`.
- Login page loads at `/login` and authenticates a user against the backend token endpoint.
- Authenticated users are routed to the correct dashboard or role-specific home page.
- Unauthorized users are blocked from role-restricted pages.
- Factory onboarding captures setup information for factory details, machines, materials, workers, customers, and completion.
- Inventory page lists and manages raw materials, packaging materials, and finished goods.
- Production page records daily production and validates required production fields.
- Sales page records sales orders and updates customer balances.
- Customers page manages customers and storefront portal links.
- Outstanding page displays pending customer balances.
- Payments page records collections against customer balances.
- Expenses page records factory expenses.
- Attendance page records worker presence, overtime, advances, and settlement data.
- Calculator page computes ideal production cost and compares ideal versus actual costs.
- AI supervisor page accepts user messages and returns operational answers or actions.
- Public storefront pages load at `/store/:storeToken` and `/storefront/:storeToken`, display available products, require terms acceptance, and create orders.

## Critical Backend Flows

- `GET /health` returns service health.
- `POST /token` returns a bearer token for valid credentials and rejects invalid credentials.
- Authenticated API routes reject requests without a valid token.
- Onboarding endpoints persist setup data for the authenticated user's factory.
- Inventory endpoints validate quantities and keep stock scoped to the authenticated user's factory.
- Production endpoints validate production inputs and update relevant production and stock records.
- Sales endpoints create invoices/orders and update outstanding balances.
- Payment endpoints record collections and reduce outstanding balances.
- Attendance endpoints store presence, overtime, advances, and settlement records.
- Billing endpoints enforce subscription and payment status.
- Storefront endpoints support public product browsing and order creation for valid store tokens.

## Acceptance Criteria

- The frontend and backend are reachable before tests begin.
- TestSprite can discover frontend routes and backend OpenAPI endpoints.
- Role-based access control prevents unauthorized page and API access.
- Valid forms submit successfully and show updated data.
- Invalid forms show validation failures and do not create bad records.
- Authenticated data is scoped by factory.
- Public storefront flow works without login but only for a valid store token.
- Backend errors are surfaced as user-visible failures instead of silent UI breaks.

## Known Test Data Notes

- Use `.env` local default users for login credentials.
- Use non-production test data only.
- Avoid relying on external services such as OpenAI, Razorpay, WhatsApp, Telegram, or n8n unless the local environment has valid test credentials configured.
