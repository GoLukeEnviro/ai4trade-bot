# AI Boundary -- Isolationsregeln

**Status:** Implementiert (Phase 2.4)
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- AI-Call Isolation und Kapselung

---

## 1. Grundregel

> **AI ISOLATION:** Kein direkter LLM-Call (Claude/OpenAI) ausserhalb des `ai/` Packages.

Diese Regel ist architektonisch durchgesetzt, nicht nur durch Konvention.

---

## 2. AI-Komponenten (`ai/` Package)

### Verzeichnisstruktur

```
ai/
    __init__.py
    sentiment.py              # Sentiment-Analyse (einziger Entry-Point)
    guardrails.py             # Score-Clamping, JSON-Parsing
    validation.py             # Response-Validierung
    providers/
        __init__.py
        base.py               # Abstraktes Provider-Interface
        claude_provider.py    # Anthropic Claude
        openai_provider.py    # OpenAI-kompatibel
        factory.py            # Provider-Auswahl via LLM_PROVIDER
```

### Was AI macht

| Funktion | Beschreibung | Datei |
|----------|-------------|-------|
| Sentiment | News-Sentiment als Score [-1.0, +1.0] | `ai/sentiment.py` |
| Score Clamping | Begrenzung auf gueltigen Wertebereich | `ai/guardrails.py` |
| JSON-Parsing | Sichere LLM-Response-Extraktion | `ai/guardrails.py` |
| Response-Validierung | Struktur-Check der LLM-Antwort | `ai/validation.py` |

### Was AI NICHT macht

| Verboten | Begruendung |
|----------|-------------|
| Rohe Execution-Entscheidungen | Strategy entscheidet, AI liefert nur Input |
| Direkte Orders | Execution Service hat keinen AI-Kontakt |
| Price-Entscheidungen | Preise kommen von Exchange, nicht von AI |
| Risk-Management | Risk Gate arbeitet rein regelbasiert |

---

## 3. Durchsetzung

### Package-Kapselung

- `ai/` ist das einzige Package, das LLM-Clients importiert
- Alle anderen Module importieren nur das `ai/` Interface
- `core/sentiment.py` existiert nicht -- Sentiment geht ueber `ai/sentiment.py`

### Guardrails

```python
# ai/guardrails.py
clamp_score(score, min_val=-1.0, max_val=1.0)    # Sentiment-Bereich
clamp_confidence(confidence)                       # [0.0, 1.0]
safe_json_parse(text)                              # Kein Absturz bei kaputtem JSON
```

### Validation

- LLM-Responses werden auf erwartete Struktur geprueft
- Fehlende oder ungueltige Felder fuehren zu Defaults (nie zu Abstuerzen)
- Jeder LLM-Call hat einen Fallback-Wert

---

## 4. Provider-Abstraktion

```python
# ai/providers/base.py
class LLMProvider(Protocol):
    def complete(self, prompt: str, system: str = "") -> str: ...
    def complete_json(self, prompt: str, system: str = "") -> dict: ...
```

- Provider-Auswahl via `LLM_PROVIDER` (Default: `claude`)
- Factory-Pattern in `ai/providers/factory.py`
- Keine Provider-spezifischen Details nach aussen

---

## 5. Referenzen

- AI Package: `ai/`
- Guardrails: `ai/guardrails.py`
- Provider-Interface: `ai/providers/base.py`
- Architektur-Doku: `docs/context/bitget-mcp-hybrid-architecture.md` (ADR-4)

---

## 6. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Design-Dokumentation | 2.4 |
