#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "ERROR: Docker Compose is not installed." >&2
  exit 1
fi

cd "$APP_DIR"

echo "==> Pulling latest repository changes"
git pull --ff-only

echo "==> Stopping existing containers"
"${COMPOSE[@]}" down

echo "==> Rebuilding and starting production stack"
"${COMPOSE[@]}" up -d --build

echo "==> Removing unused Docker images"
docker image prune -f

echo "==> Restarting Caddy to reload configuration"
"${COMPOSE[@]}" restart caddy

echo "==> Deployment complete"
"${COMPOSE[@]}" ps
