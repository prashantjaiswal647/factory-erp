#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PRODUCTION_DOMAIN="${PRODUCTION_DOMAIN:-https://munshiai.co.in}"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "ERROR: Docker Compose is not installed." >&2
  exit 1
fi

cd "$APP_DIR"

echo "==> Running pre-deployment validation gate"
./validate-and-test.sh

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: Working tree has uncommitted changes. Commit or stash before production deploy." >&2
  git status --short
  exit 1
fi

echo "==> Pulling latest repository changes"
git pull --ff-only

echo "==> Ensuring database is running before backup"
VITE_API_URL="${PRODUCTION_DOMAIN}" CORS_ORIGINS="${PRODUCTION_DOMAIN},https://www.munshiai.co.in" "${COMPOSE[@]}" up -d postgres

BACKUP_DIR="${APP_DIR}/storage/backups"
BACKUP_FILE="${BACKUP_DIR}/pre_alembic_$(date +%F_%H%M%S).dump"
mkdir -p "${BACKUP_DIR}"

echo "==> Creating pre-migration PostgreSQL backup"
"${COMPOSE[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "${BACKUP_FILE}"
echo "==> Backup created: ${BACKUP_FILE}"

echo "==> Rebuilding api and web with no cache for ${PRODUCTION_DOMAIN}"
VITE_API_URL="${PRODUCTION_DOMAIN}" CORS_ORIGINS="${PRODUCTION_DOMAIN},https://www.munshiai.co.in" "${COMPOSE[@]}" build --pull --no-cache api web

echo "==> Starting database dependencies"
VITE_API_URL="${PRODUCTION_DOMAIN}" CORS_ORIGINS="${PRODUCTION_DOMAIN},https://www.munshiai.co.in" "${COMPOSE[@]}" up -d postgres redis

echo "==> Applying Alembic database migrations"
VITE_API_URL="${PRODUCTION_DOMAIN}" CORS_ORIGINS="${PRODUCTION_DOMAIN},https://www.munshiai.co.in" "${COMPOSE[@]}" run --rm api alembic upgrade head

echo "==> Starting production stack"
VITE_API_URL="${PRODUCTION_DOMAIN}" CORS_ORIGINS="${PRODUCTION_DOMAIN},https://www.munshiai.co.in" "${COMPOSE[@]}" up -d --force-recreate

echo "==> Removing unused Docker images"
docker image prune -f
docker builder prune -f

if "${COMPOSE[@]}" ps --services | grep -qx caddy; then
  echo "==> Restarting Caddy to reload configuration"
  "${COMPOSE[@]}" restart caddy
else
  echo "==> Caddy service is not defined in docker-compose.yml; skipping Caddy restart"
fi

HEALTH_URL="https://munshiai.co.in/api/health"
HEALTH_MAX_ATTEMPTS=30
HEALTH_SLEEP_SECONDS=3

echo "==> Verifying production health endpoint: ${HEALTH_URL}"
for HEALTH_ATTEMPT in $(seq 1 "${HEALTH_MAX_ATTEMPTS}"); do
  HTTP_STATUS="$(curl -sS -o /dev/null -w "%{http_code}" "${HEALTH_URL}" || true)"

  if [[ "${HTTP_STATUS}" == "200" ]]; then
    echo "==> Production health endpoint is healthy"
    break
  fi

  if [[ "${HEALTH_ATTEMPT}" == "${HEALTH_MAX_ATTEMPTS}" ]]; then
    echo "ERROR: Production health endpoint did not return HTTP 200 after ${HEALTH_MAX_ATTEMPTS} attempts. Last status: ${HTTP_STATUS}" >&2
    echo "==> Docker Compose status"
    "${COMPOSE[@]}" ps || true
    echo "==> Last 100 API logs"
    "${COMPOSE[@]}" logs --tail=100 api || true
    echo "==> Last 100 Caddy logs"
    "${COMPOSE[@]}" logs --tail=100 caddy || true
    exit 1
  fi

  echo "==> Health endpoint not ready yet. Attempt ${HEALTH_ATTEMPT}/${HEALTH_MAX_ATTEMPTS}, status: ${HTTP_STATUS}. Retrying in ${HEALTH_SLEEP_SECONDS}s..."
  sleep "${HEALTH_SLEEP_SECONDS}"
done

echo "==> Deployment complete"
"${COMPOSE[@]}" ps
