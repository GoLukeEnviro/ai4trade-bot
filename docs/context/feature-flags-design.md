# Feature Flags -- Interface-Design

**Status:** Konzept, nicht implementiert
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- Feature-Toggles fuer schrittweise Aktivierung

---

## 1. Uebersicht

Feature Flags steuern die Aktivierung von Pipeline-Komponenten zur Laufzeit. Konfiguration erfolgt ueber Umgebungsvariablen oder YAML -- kein Redis, kein LaunchDarkly. KISS-Prinzip fuer ein Single-Instance-System.

---

## 2. Interface

```python
class FeatureFlags(Protocol):
    def is_enabled(self, flag_name: str) -> bool: ...
```

Minimales Interface: Ein Methodenaufruf, ein Boolean. Keine komplexe Evaluierung, kein Percentage-Rollout.

---

## 3. Definierte Flags

| Flag | Default | Zweck |
|------|---------|-------|
| `exchange_websocket` | `false` | WebSocket statt REST-Polling |
| `shadow_mode` | `false` | Shadow Executor aktiv (simulierte Trades) |
| `ai_provider_openai` | `false` | OpenAI als LLM-Provider (sonst Claude) |
| `execution_live` | `false` | Echte Order-Ausfuehrung (hoechste Sicherheitsstufe) |
| `event_bus_active` | `false` | InMemoryEventBus statt NoOpEventBus |
| `audit_snapshots` | `false` | TA/Sentiment-Snapshots speichern (fuer Replay) |

---

## 4. Konfiguration

### Option A: Umgebungsvariablen

```bash
FEATURE_EXCHANGE_WEBSOCKET=false
FEATURE_SHADOW_MODE=false
FEATURE_AI_PROVIDER_OPENAI=false
FEATURE_EXECUTION_LIVE=false
```

### Option B: YAML (zukuenftig)

```yaml
feature_flags:
  exchange_websocket: false
  shadow_mode: false
  ai_provider_openai: false
  execution_live: false
```

### Begruendung

- **Kein Redis/LaunchDarkly:** Single-Instance, kein verteiltes System
- **Keine Laufzeit-Aenderung:** Flags werden beim Bot-Start gelesen, Aenderung erfordert Restart
- **Einfacher geht nicht:** Ein Env-Var, ein Boolean

---

## 5. Integration

### Verwendung (zukuenftig)

```python
flags = create_feature_flags()  # EnvFeatureFlags oder YamlFeatureFlags

if flags.is_enabled("exchange_websocket"):
    exchange = WebSocketExchange()
else:
    exchange = BitgetREST()
```

### Datei

`core/feature_flags.py` -- zukuenftige Implementierung.

### Sicherheits-Integration

Das `execution_live` Flag ist nicht ausreichend fuer Live-Modus. Es ist eine von vier dry_run-Schichten (siehe Architektur-Doku, Abschnitt 5.1). Das Flag allein aktiviert keine echten Orders.

---

## 6. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Design-Dokumentation | -- |
