# \# Munshi AI - Codex Instructions

# 

# \## Project

# Munshi AI is an AI-powered Smart ERP / Factory Supervisor SaaS for paper cup/glass manufacturing units.

# 

# \## Stack

# \- Backend: FastAPI

# \- Frontend: React + Vite

# \- Database: PostgreSQL

# \- Deployment: Docker Compose on Hostinger VPS

# \- Reverse Proxy: Caddy

# \- Automation: n8n

# 

# \## Live URLs

# \- Dashboard: https://munshiai.co.in

# \- API Base: https://munshiai.co.in/api

# \- n8n: https://n8n.munshiai.co.in

# 

# \## Golden Rules

# \- Never break multi-tenant `factory\_id` architecture.

# \- Always make backend and frontend changes together when a feature requires both.

# \- Do not modify production deployment, Docker, Caddy, env, or database migration files unless the task clearly requires it.

# \- Before changing anything, inspect existing routes, schemas, models, services, and frontend API calls.

# \- Keep UI mobile-friendly and avoid horizontal scrolling.

# \- Prefer small, safe, incremental changes.

# \- Show all files changed after completing the task.

# \- Explain how to test locally and what to deploy on Hostinger.

# 

# \## Backend Rules

# \- Maintain FastAPI structure.

# \- Validate all request/response schemas.

# \- Preserve existing database compatibility.

# \- Any manual PostgreSQL changes must reflect correctly in backend APIs and frontend UI.

# 

# \## Frontend Rules

# \- React/Vite code should remain clean and component-based.

# \- Improve readability and UX without breaking existing business logic.

# \- Dashboard and inventory pages should show structured data clearly.

# 

# \## Deployment Rules

# Local development path:

# C:\\Users\\Prashant\\OneDrive\\Desktop\\Coding Projects\\ai-erp-system

# 

# Production folder on VPS:

# \~/factory-erp

# 

# Deployment flow:

# 1\. Local changes

# 2\. Test locally

# 3\. git add .

# 4\. git commit

# 5\. git push origin main

# 6\. SSH to VPS

# 7\. cd \~/factory-erp

# 8\. git pull origin main

# 9\. docker-compose up -d --force-recreate --build web caddy api

# 10\. Reload Caddy if needed

# 

# \## Response Style

# When I give a prompt:

# 1\. First inspect the relevant code.

# 2\. Then explain the plan briefly.

# 3\. Then make the changes.

# 4\. Then tell me exact test commands.

# 5\. Then give deployment commands.

