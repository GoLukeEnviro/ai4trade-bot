const API_BASE = "/api";
const POLL_INTERVAL_MS = 5000;

const errors = [];

function statusClass(value) {
  if (!value) return "";
  const normalized = String(value).toLowerCase();
  if (normalized === "healthy" || normalized === "running") return "healthy";
  if (normalized === "error" || normalized === "unhealthy") return "error";
  return "";
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("de-DE");
}

function rainbowScore(signal) {
  const features = signal.features || {};
  return (
    features.rainbow_score ??
    features.strength ??
    features.score ??
    signal.confidence ??
    "-"
  );
}

async function fetchJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${path} -> HTTP ${response.status}`);
  }
  return response.json();
}

function renderHealth(health) {
  const overall = document.getElementById("overall-status");
  overall.textContent = health.status || "unknown";
  overall.className = `status ${statusClass(health.status)}`;

  document.getElementById("health").innerHTML = `
    <div class="metric">Uptime: ${health.uptime_seconds ?? "-"}s</div>
    <div>Service-Status: <span class="status ${statusClass(health.status)}">${health.status || "-"}</span></div>
  `;

  const tbody = document.querySelector("#collectors-table tbody");
  tbody.innerHTML = "";
  const collectors = health.collectors || {};
  Object.entries(collectors).forEach(([name, state]) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${name}</td>
      <td><span class="status ${statusClass(state)}">${state}</span></td>
    `;
    tbody.appendChild(row);
    if (String(state).toLowerCase() === "error") {
      errors.push(`Collector '${name}' meldet error`);
    }
  });
}

function renderSignals(signals) {
  const tbody = document.querySelector("#signals-table tbody");
  tbody.innerHTML = "";
  if (!signals.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="6">Keine Signale vorhanden</td>`;
    tbody.appendChild(row);
    return;
  }

  signals.forEach((signal) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${signal.asset ?? "-"}</td>
      <td>${signal.class ?? signal.signal_class ?? "-"}</td>
      <td>${signal.direction ?? "-"}</td>
      <td>${signal.confidence ?? "-"}</td>
      <td>${rainbowScore(signal)}</td>
      <td>${formatTime(signal.created_at)}</td>
    `;
    tbody.appendChild(row);
  });
}

function renderMetrics(metrics) {
  document.getElementById("metrics").innerHTML = `
    <div class="metric">Signals stored: ${metrics.signals_stored_count ?? 0}</div>
    <div class="metric">Collectors active: ${metrics.collectors_active ?? 0} / ${metrics.collectors_total ?? 0}</div>
  `;
}

function renderErrors() {
  const unique = [...new Set(errors)].slice(-20);
  document.getElementById("errors").textContent = unique.length
    ? unique.join("\n")
    : "Keine Fehler";
}

async function poll() {
  errors.length = 0;
  try {
    const [health, signals, metrics] = await Promise.all([
      fetchJson("/health"),
      fetchJson("/signals/canonical/latest?limit=20"),
      fetchJson("/metrics"),
    ]);
    renderHealth(health);
    renderSignals(signals);
    renderMetrics(metrics);
    document.getElementById("last-update").textContent = new Date().toLocaleString("de-DE");
  } catch (err) {
    errors.push(String(err));
    document.getElementById("overall-status").textContent = "error";
    document.getElementById("overall-status").className = "status error";
  }
  renderErrors();
}

poll();
setInterval(poll, POLL_INTERVAL_MS);