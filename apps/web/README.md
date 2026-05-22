# Munshi AI Web

## Playwright E2E Tests

Install dependencies and browser binaries from `apps/web`:

```bash
npm install
npx playwright install
```

### Environment

Copy `.env.example` if you want stable test credentials, or export variables in your shell:

```bash
PLAYWRIGHT_BASE_URL=
PLAYWRIGHT_TEST_EMAIL=
PLAYWRIGHT_TEST_PHONE=
PLAYWRIGHT_TEST_PASSWORD=
PLAYWRIGHT_TEST_FACTORY_NAME=
```

Local tests generate a unique local owner account when these variables are omitted. Production tests never create users and only run authenticated checks when test credentials are provided.

### Local Full Flow

Start the FastAPI backend separately on `http://localhost:8000`. The Playwright config starts Vite automatically on `http://localhost:5173`.

```bash
npm run test:e2e:local
```

Local coverage includes signup validation, country-code defaults, signup, phone-only login, auth storage, dashboard load, protected route access, and representative form validation/submission checks.

### Production Smoke

Production smoke is read-only unless you provide explicit test-account credentials.

```bash
PLAYWRIGHT_BASE_URL=https://munshiai.co.in npm run test:e2e:prod
```

PowerShell:

```powershell
$env:PLAYWRIGHT_BASE_URL="https://munshiai.co.in"; npm run test:e2e:prod
```

Authenticated production smoke:

```powershell
$env:PLAYWRIGHT_BASE_URL="https://munshiai.co.in"
$env:PLAYWRIGHT_TEST_EMAIL="test@example.com"
$env:PLAYWRIGHT_TEST_PASSWORD="..."
npm run test:e2e:prod
```

### Debugging

```bash
npm run test:e2e:headed
npm run test:e2e:ui
npm run test:e2e:report
```

The shared diagnostics fixture captures browser console errors, failed network requests, and API 4xx/5xx responses. Screenshots and videos are retained only on failure. Traces are captured on first retry.

If local full-flow tests expose app bugs that are not safe obvious fixes, document them in `BUG_REPORT.md` with reproduction steps, expected/actual behavior, artifact paths, and a focused Codex fix prompt.
