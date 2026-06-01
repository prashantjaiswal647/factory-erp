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

echo "==> Stopping existing containers"
"${COMPOSE[@]}" down --remove-orphans

echo "==> Rebuilding api and web with no cache for ${PRODUCTION_DOMAIN}"
VITE_API_URL="${PRODUCTION_DOMAIN}" CORS_ORIGINS="${PRODUCTION_DOMAIN},https://www.munshiai.co.in" "${COMPOSE[@]}" build --pull --no-cache api web

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

echo "==> Verifying production health endpoint"
curl -fsS "${PRODUCTION_DOMAIN}/api/health" >/dev/null

echo "==> Deployment complete"
"${COMPOSE[@]}" ps
