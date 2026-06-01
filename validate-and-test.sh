#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="${ROOT_DIR}/apps/web"
API_DIR="${ROOT_DIR}/apps/api"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-ai-erp-validate}"
COMPOSE_FILE="${VALIDATE_COMPOSE_FILE:-${ROOT_DIR}/docker-compose.validate.yml}"
VALIDATE_API_PORT="${VALIDATE_API_PORT:-18000}"
VALIDATE_WEB_PORT="${VALIDATE_WEB_PORT:-13000}"
API_HEALTH_URL="${API_HEALTH_URL:-http://127.0.0.1:${VALIDATE_API_PORT}/api/health}"
WEB_HEALTH_URL="${WEB_HEALTH_URL:-http://127.0.0.1:${VALIDATE_WEB_PORT}/}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "ERROR: Docker Compose is not installed." >&2
  exit 1
fi

cleanup() {
  "${COMPOSE[@]}" -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup ERR

echo "==> Step A: Backend syntax and style gate"
if command -v flake8 >/dev/null 2>&1; then
  flake8 "${API_DIR}"
else
  echo "flake8 not found; using Python compile gate"
  "${PYTHON_BIN}" -m compileall -q "${API_DIR}"
fi

echo "==> Step A: Frontend TypeScript gate"
cd "${WEB_DIR}"
npm run build

echo "==> Step B: Isolated Docker build gate"
cd "${ROOT_DIR}"
VITE_API_URL="${VITE_API_URL:-}" "${COMPOSE[@]}" -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" build --no-cache api web

echo "==> Step B: Isolated container startup gate"
VITE_API_URL="${VITE_API_URL:-}" "${COMPOSE[@]}" -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" up -d --build --force-recreate postgres redis api web

echo "==> Waiting for FastAPI health"
for attempt in {1..60}; do
  if curl -fsS "${API_HEALTH_URL}" >/dev/null; then
    break
  fi
  if [ "${attempt}" -eq 60 ]; then
    echo "ERROR: API health check failed at ${API_HEALTH_URL}" >&2
    "${COMPOSE[@]}" -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" logs api >&2
    exit 1
  fi
  sleep 2
done

echo "==> Waiting for web health"
for attempt in {1..60}; do
  if curl -fsS "${WEB_HEALTH_URL}" >/dev/null; then
    break
  fi
  if [ "${attempt}" -eq 60 ]; then
    echo "ERROR: Web health check failed at ${WEB_HEALTH_URL}" >&2
    "${COMPOSE[@]}" -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" logs web >&2
    exit 1
  fi
  sleep 2
done

echo "==> Step C: Strict gate passed"
cleanup
