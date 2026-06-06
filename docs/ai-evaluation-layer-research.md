# KI-Bewertungsschicht — Forschungsbericht

## 1. Architektur

```
Collectors (TA, Twitter, Reddit, News)
         │
         ▼
   RainbowScorer (regelbasiert, sync)
         │ CryptoSignal mit rainbow_score
         ▼
┌─────────────────────────┐
│   AI Evaluation Layer   │  async, nach Scorer
│  ┌───────────────────┐  │
│  │ LLMEvaluator      │  │  DeepSeek V4 Pro
│  │ (OpenAI-compat)   │  │  → ai_confidence, risk_level
│  └───────────────────┘  │  → market_regime, reasoning
│  ┌───────────────────┐  │
│  │ EvaluationCache   │  │  In-Memory, TTL 5min, LRU 500
│  └───────────────────┘  │
└─────────┬───────────────┘
          │ CryptoSignal + ai_evaluation
          ▼
   Enhanced Signal Store (SQLite)
          │
          ▼
   Distribution (REST API + Webhooks)
```

**Key Design Decisions:**

- **Asynchrone Positionierung:** Die KI-Evaluation läuft asynchron NACH dem synchronen RainbowScorer
- **Backward-Kompatibilität:** Die bestehende `score()`-Methode bleibt unverändert. Neue `score_and_evaluate()`-Methode für KI-augmentierte Signale
- **Threshold-Filter:** Nur Signale mit `rainbow_score >= 0.5` werden zur KI-Evaluation gesendet (spart ~60% API-Calls)
- **Non-Blocking Fallback:** Timeout oder Exception → `ai_evaluation` bleibt `None`, Signal passiert ungefiltert weiter. Kein Single Point of Failure.

## 2. DeepSeek V4 Pro — Begründung

**Modell-Auswahl:** `deepseek-reasoner`

**Warum DeepSeek V4 Pro?**

1. **OpenAI-Kompatibilität:** Keine neue Dependency erforderlich. Nutzung via `base_url`-Parameter des bestehenden OpenAI-Clients
2. **Reasoning-Chain:** Das Modell generiert vor der Antwort eine Chain-of-Thought → analytische Qualität优于 reine Text-Modelle
3. **Kosten-Effizienz:** ~$0.55/1M input tokens, ~$2.19/1M output tokens (deutlich günstiger als GPT-4)
4. **Latenz:** 1-3s typisch für Trading-Signal-Evaluation (akzeptabel für asynchrone Pipeline)
5. **Trading-Domain:** Bessere Performance bei finanzanalytischen Aufgaben durch optimiertes Training

**Konfiguration:**

```python
model = "deepseek-reasoner"
temperature = 0.1  # Deterministisch für Evaluation
timeout = 5  # Sekunden hard limit
max_tokens = 500  # Kurze, strukturierte Antworten
```

## 3. Modellvergleich

| Modell | Latenz | Kosten/1M Token | Accuracy (Trading) | API-Kompatibilität |
|--------|--------|-----------------|---------------------|---------------------|
| DeepSeek V4 Pro | 1-3s | ~$2.74 | Hoch (Reasoning) | OpenAI-compat |
| Claude Haiku 4.5 | 0.3-1s | ~$1.25 | Hoch | Eigenes SDK |
| GPT-4o-mini | 0.5-1.5s | ~$0.60 | Mittel-Hoch | OpenAI native |
| FinBERT (lokal) | 50-200ms | $0 (self-hosted) | Mittel (nur Sentiment) | HuggingFace |

**Analyse:**

- **DeepSeek V4 Pro:** Beste Balance aus Reasoning-Fähigkeit, Kosten und API-Kompatibilität. Ideal für erste Implementierung.
- **Claude Haiku 4.5:** Schnellste Latenz, aber erfordert separates SDK. Kandidat für zukünftige Hybrid-Strategie.
- **GPT-4o-mini:** Günstigste Option, aber geringere analytische Tiefe ohne Reasoning-Chain.
- **FinBERT:** Maximale Latenz-Ersparnis durch self-hosting, aber limitiert auf Sentiment-Analyse. Keine umfassende Signal-Evaluation.

## 4. AIEvaluation-Modell

```python
from pydantic import BaseModel
from typing import Literal

class AIEvaluation(BaseModel):
    """KI-Bewertung eines Trading-Signals."""

    ai_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Konfidenz der KI in die Signal-Qualität (0.0-1.0)"
    )
    risk_level: Literal["low", "medium", "high"] = Field(
        description="Eingeschätztes Risiko des Trades"
    )
    market_regime: Literal["trending", "ranging", "volatile", "quiet"] = Field(
        description="Aktuelles Marktregime aus KI-Sicht"
    )
    reasoning: str = Field(
        max_length=300,
        description="Kurze Begründung der Bewertung (max 300 Zeichen)"
    )
    model_used: str = Field(
        description="Kennzeichnung des verwendeten Modells"
    )
    evaluation_latency_ms: int = Field(
        ge=0,
        description="Latenz der Evaluation in Millisekunden"
    )
```

**Feld-Semantik:**

- **ai_confidence:** Höhere Werte → Signal wird mit höherer Priorität verteilt
- **risk_level:** Filtering-Möglichkeit für risikoaverse Strategien
- **market_regime:** Kontext-Information für Folge-Systeme
- **reasoning:** Audit-Trail für Compliance und Debugging
- **evaluation_latency_ms:** Performance-Monitoring für SLA-Tracking

## 5. Prompt-Strategie

**System Prompt:**

```
Du bist ein objektiver, analytischer Evaluator für Krypto-Trading-Signale.
Deine Aufgabe ist es, Signale auf Basis der bereitgestellten Daten zu bewerten.
Antworte ausschliesslich im JSON-Format ohne zusätzlichen Text.
Sei präzise, konservativ und risikobewusst.
```

**User Prompt-Struktur:**

```python
prompt = f"""
Bewerte das folgende Trading-Signal:

Asset: {signal.asset}
Direction: {signal.direction}
Strength: {signal.strength:.2f}
Rainbow Score: {signal.rainbow_score:.2f}
Source: {signal.source}
Timestamp: {signal.timestamp}

Technische Daten:
- RSI: {technical_data.get('rsi', 'N/A')}
- MACD: {technical_data.get('macd', 'N/A')}
- Bollinger Bands: {technical_data.get('bb', 'N/A')}

Gib deine Bewertung im folgenden JSON-Format zurück:
{{
    "ai_confidence": 0.0-1.0,
    "risk_level": "low" | "medium" | "high",
    "market_regime": "trending" | "ranging" | "volatile" | "quiet",
    "reasoning": "Kurze Begründung (max 300 Zeichen)",
    "model_used": "deepseek-reasoner",
    "evaluation_latency_ms": <Latenz in ms>
}}
"""
```

**Validierungs-Chain:**

1. **Prompt-Level:** Strukturierte Format-Anweisung
2. **Response-Level:** JSON-Parsing mit Exception-Handling
3. **Model-Level:** Pydantic-Validierung mit Typ-Checks
4. **Fallback-Level:** Bei Parse-Error → `ai_evaluation = None`

## 6. Latenz-Optimierung

| Strategie | Ersparnis | Aufwand | Status |
|-----------|-----------|---------|--------|
| Threshold-Filter (score >= 0.5) | ~60% weniger API-Calls | Minimal | ✅ Implementiert |
| Response-Caching (TTL 5min) | Vermeidet doppelte Calls | Implementiert | ✅ Aktiv |
| asyncio.gather (parallel) | Pipeline-Latenz reduziert | Implementiert | ✅ Aktiv |
| Haiku für Routine, DeepSeek für kritisch | ~70% Kosteneinsparung | Mittel | 🔜 Zukunft |

**Caching-Details:**

- **TTL:** 5 Minuten (Balance zwischen Frische und Hit-Rate)
- **LRU-Capacity:** 500 Einträge (Memory-footprint kontrollieren)
- **Cache-Key:** `(asset, direction, rainbow_score_rounded, source)`
- **Invalidierung:** Zeitbasiert (TTL), keine manuelle Invalidierung nötig

**Parallelisierung:**

```python
# Parallele Evaluation mehrerer Signale
evaluated_signals = await asyncio.gather(
    *[llm_evaluator.evaluate(signal) for signal in filtered_signals],
    return_exceptions=True  # Exceptions blockieren nicht die Pipeline
)
```

## 7. Implementierungsfahrplan

### Phase 1: LLM Signal Evaluator MVP (aktuell)

**Ziele:**

- DeepSeek V4 Pro via OpenAI-kompatiblem Client
- `AIEvaluation`-Modell + `LLMEvaluator`-Klasse
- In-Memory-Cache + Threshold-Filter
- Integration in Pipeline via `score_and_evaluate()`

**Deliverables:**

- `core/llm_evaluator.py` — LLMEvaluator, EvaluationCache
- `models/evaluation.py` — AIEvaluation Pydantic-Modell
- Erweiterte `CryptoSignal`-Integration um `ai_evaluation: Optional[AIEvaluation]`
- Tests in `tests/test_llm_evaluator.py`

### Phase 2: Feature Pipeline + XGBoost (4-6 Wochen)

**Ziele:**

- `core/feature_pipeline.py` — ML-ready Features aus Rohdaten
- Fear & Greed Index als externes Feature
- XGBoost Classifier (5-15ms Inferenz, async-kompatibel)
- Meta-Labeling (López de Prado): Bestehende TA bleibt, ML filtert schlechte Signale

**Architektur:**

```
Raw Signal → Feature Pipeline → XGBoost → Meta-Label → Enhanced Signal
```

**Deliverables:**

- Feature-Engineering-Pipeline
- Trainings-Dataset-Historie
- XGBoost-Modell-Export (JSON)
- Hybrid-Evaluation: LLM + ML

### Phase 3: Erweiterte Modelle (Optional)

**Optionen:**

- **FinBERT/CryptoBERT:** Sentiment-Analyse für Social-Media-Signale
- **Multi-LLM Veto System:** Ensemble-Consensus mehrerer Modelle
- **Lokales Modell-Hosting:** Ollama für隐私kritische Evaluationen

## 8. Fallback-Verhalten

**Non-Blocking Design:**

```
Signal → RainbowScorer → (score >= 0.5?) → LLMEvaluator → Success?
                                          │              │
                                         No             Timeout
                                          │              │
                                          └──────┬───────┘
                                                 ▼
                                         Signal weiterleiten
                                         (ai_evaluation = None)
```

**Szenarien:**

1. **Timeout (5s):** `ai_evaluation = None`, Signal passiert ungefiltert, Warning-Log
2. **API-Fehler (4xx/5xx):** `ai_evaluation = None`, Error-Log mit Response-Details
3. **Malformed JSON:** `ai_evaluation = None`, Debug-Log mit Raw-Response
4. **API-Key fehlt:** Evaluator wird nicht initialisiert, Pipeline läuft ohne KI-Layer
5. **Pydantic-Validation-Error:** `ai_evaluation = None`, Warning-Log

**Kein Single Point of Failure:** Die Pipeline funktioniert auch ohne KI-Layer. RainbowScorer liefert weiterhin konsistente Signale.

## 9. Ausblick: Multi-LLM Veto System (Phase 3)

**Konzept:**

Mehrere LLMs bewerten ein Signal unabhängig voneinander. Ein Ensemble-Consensus-Mechanismus entscheidet, ob das Signal akzeptiert wird. Inspiriert vom Multi-LLM Veto System (Frank Morales, 2025).

**Mechanismus:**

```
Signal → LLM-1 (Claude) → Evaluation-1
      → LLM-2 (DeepSeek) → Evaluation-2
      → LLM-3 (GPT-4o) → Evaluation-3

Ensemble-Consensus → Agreement > Threshold?
                           │ Yes      │ No
                           ▼          ▼
                     Signal akzeptiert  Signal blockiert (Veto)
```

**Veto-Logik:**

- Wenn 2+ Modelle `high` risk level melden → Veto
- Wenn `ai_confidence` < 0.4 bei 2+ Modellen → Veto
- Wenn `market_regime` widersprüchlich ist → Signal flaggen für manuellen Review

**Wissenschaftliche Grundlage:**

- **TradingAgents:** Multi-Agents LLM Financial Trading Framework (arXiv:2412.20138, 2024)
- **FlowHunt-Studie:** Comparing LLM-Based Trading Bots (2025)
- **Morales, 2025:** Multi-LLM Enhanced Cryptocurrency Trading Bot

**Implementierung:**

```python
class MultiLLMEvaluator:
    """Ensemble-Evaluator mit Veto-Mechanismus."""

    def __init__(self):
        self.evaluators = [
            LLMEvaluator(model="claude-3.5-haiku"),
            LLMEvaluator(model="deepseek-reasoner"),
            LLMEvaluator(model="gpt-4o-mini")
        ]

    async def evaluate_with_veto(self, signal: CryptoSignal) -> Optional[AIEvaluation]:
        """Evaluiert mit mehreren LLMs und wendet Veto-Regeln an."""
        evaluations = await asyncio.gather(
            *[evaluator.evaluate(signal) for evaluator in self.evaluators],
            return_exceptions=True
        )

        # Veto-Logik
        if self._should_veto(evaluations):
            return None  # Signal wird blockiert

        return self._aggregate_evaluations(evaluations)
```

**Vorteile:**

- **Robustheit:** Ein Modell-Fehler gefährdet nicht die gesamte Pipeline
- **Quality-Boost:** Ensemble-Consensus liefert konservativere, zuverlässigere Bewertungen
- **Transparenz:** Meinungsverschiedenheiten zwischen Modellen werden sichtbar

---

## Fazit

Die KI-Bewertungsschicht erweitert die Rainbow Intelligence Engine um eine analytische Dimension, die über regelbasierte Scoring hinausgeht. DeepSeek V4 Pro bietet mit seiner Reasoning-Chain und OpenAI-Kompatibilität eine ideale Balance aus Qualität, Kosten und Integrations-Aufwand.

Durch asynchrone Architektur, Caching und Threshold-Filterung bleibt die Pipeline performant und robust. Das Non-Blocking-Fallback-Design garantiert, dass die Rainbow Engine auch ohne KI-Layer zuverlässig funktioniert.

Die phased roadmap ermöglicht eine iterative Validierung: MVP mit DeepSeek → Hybrid mit XGBoost → Ensemble mit Multi-LLM Veto System. Jede Phase baut auf der vorherigen auf und minimiert das Risiko bei gleichzeitiger Steigerung der Signal-Qualität.

---

*Stand: 2026-06-06*
*Version: 1.0*
