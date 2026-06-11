# Production Validation Sprint: Root Cause Report

This report outlines the root causes, locations, fixes, and verification steps for the production validation issues identified during the validation sprint.

---

## Part A: Telegram Webhook Production Failure (HTTP 500)

### 1. Root Cause Analysis
The Telegram bot receives `/start` but does not respond, and `getWebhookInfo` reports `Wrong response from the webhook: 500 Internal Server Error`.

The root cause of this failure is the **missing `briefing_snapshots` table** in the production database. 
Although the onboarding and connection flow (`_finalize_binding`) does not directly insert into the table, the nested menu callback and allowed callbacks check imported code dynamically queries the `BriefingSnapshot` model (in [telegram_onboarding.py](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/api/services/telegram_onboarding.py#L401-413)) to determine if the user has access to `briefing_history`. 

Because migration `0030` was missing on the production database, the table `briefing_snapshots` did not exist. This caused a SQL error `psycopg2.errors.UndefinedTable: relation "briefing_snapshots" does not exist`, which propagated to FastAPI and returned an HTTP 500 error to n8n/Telegram.

Additionally, if the `TELEGRAM_BOT_TOKEN` or `TELEGRAM_WEBHOOK_SECRET` environment variables are not correctly set in the production environment, the `_telegram_bot_config` or the secret header verification will raise `HTTPException` (which are handled properly with 503/401, but still prevent response delivery).

### 2. Location
- **File**: [telegram_onboarding.py](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/api/services/telegram_onboarding.py#L405-413)
- **Line**: 405 (and other usages of `BriefingSnapshot` in API routes)

### 3. Fix
- Ensure migration `0030_briefing_snapshots` is applied to the production database. This creates the `briefing_snapshots` table and resolves the SQL exception.
- Ensure the production `.env` environment variables `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET` are correctly configured.

---

## Part B: Verify Briefing History Production

### 1. Verification of Migration 0030
- The migration `0030_briefing_snapshots` has been created and verified to run successfully on SQLite in test environments.
- On the production database, ensure that the table is created by running `alembic upgrade head`.

### 2. Verification of [] (Empty List) Return
- The GET route `/api/briefings/history` (defined in [briefings.py](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/api/routers/briefings.py#L72-153)) loops through the queried snapshots and builds the list.
- If the table exists but has no data, `query.all()` returns an empty list `[]`, which is correctly serialized and returned as `[]` (HTTP 200) instead of throwing an HTTP 500 error.

---

## Part C: Verify Billing Status Endpoint (HTTP 401)

### 1. Root Cause Analysis
The authenticated dashboard receives a `401 Unauthorized` response when hitting `/api/billing/status`.

The root cause is that the `is_subscription_bypass_path` check in `apps/api/auth.py` matches by checking:
```python
def is_subscription_bypass_path(path: str) -> bool:
    return (
        path.startswith("/api/auth")
        or path.startswith("/api/billing")
        ...
    )
```
While this bypasses the subscription expired (HTTP 402) check, it **does not bypass the JWT authentication itself**. The endpoint is declared with:
```python
current_user: User = Depends(get_current_active_user)
```
which triggers the `oauth2_scheme` Bearer token extraction and decoding. If the token is missing from the request header, FastAPI's `Depends(oauth2_scheme)` automatically returns a `401 Unauthorized` response before the route handler is even invoked.

On the frontend, the Axios interceptor in [api.ts](file:///C:/Users/Prashant/OneDrive/Desktop/Coding%20Projects/ai-erp-system/apps/web/src/lib/api.ts#L49-66) reads the token from `localStorage` under `"token"` or `"ai_erp_token"`. If the token is missing, expired, or has been cleared in the client context, the header `Authorization: Bearer <token>` is not attached or rejected by the backend, resulting in a 401 error.

### 2. Verification commands:
Verify that the frontend attaches the Bearer token:
```bash
# In the browser, check the Network tab -> Request Headers for /api/billing/status
# Look for: Authorization: Bearer <JWT_TOKEN>
```

---

## Verification Commands & Expected Production Result

### 1. Migration Upgrade
Ensure Alembic migration is successfully run on production:
```bash
docker compose exec api alembic upgrade head
```

### 2. Test Execution
Verify all tests pass locally:
```bash
python -m pytest tests/test_briefing_history.py tests/test_telegram_binding.py -v
```

### 3. Frontend Build Validation
Verify that the frontend builds without TypeScript or bundling issues:
```bash
npm --prefix apps/web run build
```

### 4. Expected Production Result
- The database table `briefing_snapshots` exists.
- Hitting `/api/briefings/history` returns `[]` (HTTP 200) when there is no briefing history.
- Hitting `/api/billing/status` succeeds with HTTP 200 when a valid Bearer token is provided.
- The Telegram webhook successfully connects users without raising HTTP 500 errors.
