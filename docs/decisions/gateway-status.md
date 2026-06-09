# Gateway Status — Archived

**Status:** Archived since May 2026

## Context

The Hermes gateway was part of the early Hermes setup and was used for Telegram message routing. It ran as a long-lived service that forwarded signals and notifications from the ai4trade-bot system to a Telegram chat via the Hermes infrastructure.

## Decision

Keep the gateway **stopped**. The ai4trade-bot system now uses its own Telegram sink (`core/notifications/telegram_sink.py`, introduced in PR #37) and does not need the Hermes gateway for signal routing.

## Consequences

- No Telegram delivery via the Hermes gateway.
- All notifications go through `core/notifications/telegram_sink.py` directly.
- The gateway container can be removed from any future deployment manifests.
- If cross-profile message routing is ever needed, a dedicated lightweight forwarder should be designed rather than reviving the monolithic gateway.