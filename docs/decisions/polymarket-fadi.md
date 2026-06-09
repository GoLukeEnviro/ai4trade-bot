# Polymarket-Fadi Profile — Archived Stub

**Status:** Archived

## Context

The `polymarket-fadi` Hermes profile was created as a stub for a Polymarket paper-trading experiment. It contains only a `.env` file and minimal config — no running containers, no active skills, and no scheduled tasks.

## Decision

Archive the profile. It is not actively used and has no running containers. Keep the directory and `.env` for reference, but mark the profile as inactive.

## Consequences

- No active Polymarket trading via this profile.
- The profile directory and `.env` are retained for historical reference.
- The profile can be fully deleted in a future cleanup pass once confirmed unnecessary.
- Any future Polymarket integration should be built as a dedicated skill or plugin rather than a separate profile.