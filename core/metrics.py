from prometheus_client import Counter, Gauge, Histogram, generate_latest

SIGNALS_TOTAL = Counter(
    "bot_signals_total",
    "Total signals generated",
    ["pair", "action"],
)

SIGNALS_PUBLISHED = Counter(
    "bot_signals_published_total",
    "Signals successfully published",
    ["pair", "action"],
)

SIGNALS_BLOCKED = Counter(
    "bot_signals_blocked_total",
    "Signals blocked by risk gate",
    ["pair", "reason"],
)

API_LATENCY_SECONDS = Histogram(
    "bot_api_latency_seconds",
    "API request latency",
    ["endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

API_ERRORS_TOTAL = Counter(
    "bot_api_errors_total",
    "API errors",
    ["endpoint"],
)

DRAWDOWN_PCT = Gauge(
    "bot_drawdown_pct",
    "Current drawdown percentage",
)

OPEN_POSITIONS = Gauge(
    "bot_open_positions",
    "Number of open positions",
)

CIRCUIT_BREAKER_ACTIVE = Gauge(
    "bot_circuit_breaker_active",
    "Circuit breaker status (1=active, 0=inactive)",
)

RATE_LIMIT_WAITS = Counter(
    "bot_rate_limit_waits_total",
    "Rate limiter wait events",
    ["api"],
)

BOT_UPTIME_SECONDS = Gauge(
    "bot_uptime_seconds",
    "Bot uptime in seconds",
)

BOT_INFO = Gauge(
    "bot_info",
    "Bot information",
    ["mode", "version"],
)

CANONICAL_SIGNALS_TOTAL = Counter(
    "bot_canonical_signals_total",
    "Canonical signals processed",
    ["class", "asset"],
)

CANONICAL_RISK_BLOCKED = Counter(
    "bot_canonical_risk_blocked_total",
    "Canonical signals blocked by risk gate",
    ["reason"],
)

def get_metrics() -> bytes:
    """Prometheus-Export-Format generieren."""
    return generate_latest()
