#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docs/r4/standalone-rainbow.yml"
PROJECT_NAME="${RAINBOW_SMOKE_PROJECT:-rainbow-smoke}"
RAINBOW_PORT="${RAINBOW_PORT:-18080}"
DASHBOARD_PORT="${DASHBOARD_PORT:-18081}"
WAIT_SECONDS="${WAIT_SECONDS:-90}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SMOKE_SNAPSHOT="${RAINBOW_SMOKE_SNAPSHOT:-/tmp/${PROJECT_NAME}-r7-snapshot.json}"

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

echo "=== Read-only R7 endpoint gate (first cycle) ==="
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/r7_smoke_check.py" \
  --base-url "http://localhost:${RAINBOW_PORT}" \
  --expected-collector ta \
  --snapshot-path "${SMOKE_SNAPSHOT}"
curl -fsS "http://localhost:${DASHBOARD_PORT}/" | grep -q "Rainbow Test Dashboard"

echo "=== Waiting 60s for TA collector cycle ==="
sleep 60

echo "=== Read-only R7 endpoint gate (second cycle) ==="
"${PYTHON_BIN}" "${ROOT_DIR}/scripts/r7_smoke_check.py" \
  --base-url "http://localhost:${RAINBOW_PORT}" \
  --expected-collector ta \
  --require-signal \
  --snapshot-path "${SMOKE_SNAPSHOT}"

echo "=== Smoke test passed ==="
