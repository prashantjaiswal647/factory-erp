# Munshi AI - Secret Rotation and Environment Handling Checklist

This document details the security policies, rotation checklists, and best practices for managing local environment variables (`.env`) and secrets in both development and production environments.

## Production-Required Environment Variables

The following key configurations must be defined in production environment variables (usually managed in the deployment host environment or `.env` not tracked by git):

1. **`JWT_SECRET_KEY`**: Cryptographic secret key used to sign JSON Web Tokens for authentication.
2. **`N8N_API_KEY`**: Authentication key used to secure incoming callbacks/webhooks from n8n to the FastAPI backend.
3. **`POSTGRES_PASSWORD`**: DB administrator password for PostgreSQL instance.
4. **`SUPER_ADMIN_EMAIL`**: The email username used for Super Admin control room access.
5. **`SUPER_ADMIN_PASSWORD_HASH`**: Bcrypt hash of the Super Admin password.
6. **`SUPER_ADMIN_JWT_SECRET`**: Cryptographic secret key used to sign/verify tokens specifically for the Super Admin panel.
7. **`GROQ_API_KEY`** (if used): API access key for LLM queries/reasoning via Groq API.
8. **`OPENAI_API_KEY`**: API access key for transcribing audio notes and speech context.

---

## Secret Rotation Checklist

Rotate secrets immediately if:
- A secret is accidentally committed to version control.
- A developer leaves the project.
- There is any suspicion of a key leak or security compromise.
- Periodically (every 90 days recommended for production keys).

### Step-by-Step Key Rotation Procedure

#### 1. JWT & Super Admin Secret Keys
1. Generate new strong cryptographic keys:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Update the `.env` (development) or production service manager configuration with the new values for `JWT_SECRET_KEY` and `SUPER_ADMIN_JWT_SECRET`.
3. Restart the FastAPI service to apply the change immediately. Existing users will be forced to log in again because their old tokens will become invalid.

#### 2. Super Admin Credentials & Password Hash
1. Generate a new strong password.
2. Hash the password using the FastAPI utility or bcrypt in Python:
   ```bash
   python -c "from passlib.context import CryptContext; pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto'); print(pwd_context.hash('your_new_password'))"
   ```
3. Update `SUPER_ADMIN_EMAIL` and `SUPER_ADMIN_PASSWORD_HASH` variables.

#### 3. Database Password (`POSTGRES_PASSWORD`)
1. Change the password in the active PostgreSQL database instance.
2. Update `.env` / production config for the backend container with the new password in `DATABASE_URL`.
3. Restart the database and backend services.

#### 4. External APIs (`N8N_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`)
1. Generate new keys in the respective provider dashboards (Groq Console, OpenAI Console, n8n instance).
2. Swap the keys in the environment configurations.
3. Verify connection health by calling backend `/api/health` and hitting a sample test route.

---

## Environment Safety Guardrails

- **NEVER** stage or commit the `.env` file to Git.
- Regularly verify with `git check-ignore .env` that the environment file remains ignored.
- Use `.env.example` as the single source of truth for required keys, keeping all value assignments as placeholders only.
- In production, inject keys via a secure runtime secret manager (like Docker Secrets or VPS env vars) rather than storing static text files.
