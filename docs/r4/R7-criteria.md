# R7 — Measurement Phase Acceptance Criteria

## Zweck

Definiert die Bedingungen, unter denen Rainbow aus der 14-Tage-Testphase (R4)
in den vollständigen Multi-Collector-Betrieb (R7) übergeht.

## Mindestanforderungen (alle müssen erfüllt sein)

### Stabilität

- [ ] TA-Collector läuft ≥ 14 Tage ohne ungeplanten Neustart (Uptime > 95%)
- [ ] `/health` liefert `status: healthy` konsistent (< 5 Fehler in 14 Tagen)
- [ ] `signals_stored_count` (nach GAP-1 Fix) zeigt kontinuierliches Wachstum

### Datenqualität

- [ ] Alle 6 Signale/Zyklus werden korrekt gespeichert (BTC/ETH/SOL × 1h/4h)
- [ ] RSI, MACD, EMA, Bollinger-Werte sind plausibel (kein NaN, kein 0-Wert-Dauersignal)
- [ ] `rainbow_score` zeigt Varianz über 14 Tage (nicht immer gleicher Wert)

### Signal-Integrität

- [ ] Canonical Endpoint `/signals/canonical/latest` liefert valide Envelopes
- [ ] Jeder geprüfte Envelope hat `data_quality.status: ok`, eine nichtnegative `freshness_seconds` und ist jünger als seine `invalidation.max_age_seconds`
- [ ] `can_execute: false` bleibt in allen Envelopes gesetzt
- [ ] `dry_run_only: true` bleibt in allen Envelopes gesetzt

### Wiederholbarer Deployment-Gate

- [ ] Zwei aufeinanderfolgende Läufe von `scripts/r7_smoke_check.py` sind grün
- [ ] `signals_stored_count` sinkt zwischen diesen Läufen nicht
- [ ] Genau der erwartete TA-Collector läuft; Derivatives, LLM und Delivery bleiben deaktiviert

## Freigabe-Prozess nach R7-Evidenz

1. Sentiment-Collector (Twitter/Reddit) aktivieren — einen nach dem anderen.
2. Jede Aktivierung: 48h Beobachtung vor dem nächsten Schritt.
3. LLM-Evaluation erst aktivieren, wenn beide Sentiment-Collector stabil laufen.
4. Cross-Signal-Boost-Verhalten nach der ersten Woche Multi-Collector auswerten.

## R7-Nicht-Bestanden

- Mehr als 2 ungeplante Restarts in 14 Tagen → R4-Messphase verlängern.
- `signals_stored_count` stagniert (Insert-Bug) → vor R7 fixen.
- Bitget-API-Ausfälle > 10% der Zyklen → Fallback-Provider evaluieren.
