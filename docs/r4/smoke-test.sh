#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docs/r4/standalone-rainbow.yml"
PROJECT_NAME="${RAINBOW_SMOKE_PROJECT:-rainbow-smoke}"
RAINBOW_PORT="${RAINBOW_PORT:-18080}"
DASHBOARD_PORT="${DASHBOARD_PORT:-18081}"
WAIT_SECONDS="${WAIT_SECONDS:-90}"

cd "${ROOT_DIR}"

cleanup() {
  docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" down -v >/dev/null 2>&1 || true
}

trap cleanup EXIT

echo "=== Rainbow smoke test (${PROJECT_NAME}) ==="
docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" up -d --build

echo "=== Waiting for Rainbow health (max ${WAIT_SECONDS}s) ==="
deadline=$((SECONDS + WAIT_SECONDS))
until curl -fsS "http://localhost:${RAINBOW_PORT}/health" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "ERROR: Rainbow /health not ready within ${WAIT_SECONDS}s"
    docker compose -p "${PROJECT_NAME}" -f "${COMPOSE_FILE}" logs --tail=50 rainbow || true
    exit 1
  fi
  sleep 3
done

echo "=== Endpoint checks ==="
curl -fsS "http://localhost:${RAINBOW_PORT}/health" | tee /tmp/rainbow-health.json
curl -fsS "http://localhost:${RAINBOW_PORT}/signals/canonical/latest?limit=5" >/dev/null
curl -fsS "http://localhost:${RAINBOW_PORT}/metrics" >/dev/null
curl -fsS "http://localhost:${DASHBOARD_PORT}/" | grep -q "Rainbow Test Dashboard"

echo "=== Waiting 60s for TA collector cycle ==="
sleep 60
curl -fsS "http://localhost:${RAINBOW_PORT}/health" | tee /tmp/rainbow-health-after.json

if ! grep -q '"ta":"running"' /tmp/rainbow-health-after.json; then
  echo "WARNING: collectors.ta is not running yet"
  grep '"collectors"' /tmp/rainbow-health-after.json || true
fi

echo "=== Smoke test passed ==="