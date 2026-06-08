# AI4TradeBot LLM Signal Review Layer Plan

Date: 2026-06-08
Repo: `GoLukeEnviro/ai4trade-bot`
Status: Planning baseline for MVP implementation
Related roadmap: `docs/plans/ai4trade-signal-intelligence-layer-roadmap.md`

---

## Executive verdict

The LLM layer is not an optional gimmick. It should become the **review, explanation and synthesis layer** for the AI4TradeBot Signal & Intelligence Layer.

However, it must remain strictly bounded:

```text
LLM = evaluator / critic / explainer / summarizer
LLM != trade executor / deterministic risk gate / live authority
```

The correct MVP path is to harden and extend the already existing Rainbow `LLMEvaluator`, using **DeepSeek V4 Pro through the Ollama Cloud compatible endpoint** as the primary review model.

---

## Current repository state

### Existing LLM evaluation layer

The repo already contains:

- `rainbow/evaluation/llm_evaluator.py`
- `rainbow/evaluation/models.py`
- `rainbow/evaluation/cache.py`
- `rainbow/evaluation/context_enricher.py`
- `rainbow/processor/scorer.py`
- `rainbow/config/settings.py`

Current behavior:

1. Rainbow collectors emit `CryptoSignal` objects.
2. `RainbowScorer` computes `rainbow_score`.
3. If evaluation is enabled and score is above threshold, `LLMEvaluator.evaluate()` runs.
4. The result is stored as `AIEvaluation` on the signal.

Current `EvaluationConfig` shape:

```python
enabled: bool = False
model: str = "deepseek-reasoner"
temperature: float = 0.1
timeout_seconds: float = 5.0
threshold: float = 0.5
cache_ttl_seconds: int = 300
```

Current `AIEvaluation` shape:

```python
ai_confidence: float
risk_level: "low" | "medium" | "high"
market_regime: "trending" | "ranging" | "volatile" | "quiet"
reasoning: str
model_used: str
evaluation_latency_ms: int
```

### Important gap

The existing LLM layer is directionally correct but still too shallow for the target Signal & Intelligence Layer.

It currently lacks:

- explicit Ollama Cloud model/provider configuration;
- primary/fallback model separation;
- structured JSON response enforcement;
- schema validation / repair strategy;
- richer signal-quality output;
- contradiction detection;
- missing-context detection;
- policy-based final handling;
- optional critic model;
- compact downstream summaries for notifications and context APIs.

---

## Target architecture

```text
Canonical Signal Envelope
        |
        v
Deterministic Risk & Data-Quality Gate
        |
        v
LLM Signal Evaluator
        |
        v
Optional Risk Critic for high-impact / contradictory signals
        |
        v
Rule-Based Review Policy / Arbiter
        |
        v
Store / Summary / Alert / Context API
```

### Non-negotiable safety rule

The final handling decision must be determined by a rule-based policy that considers deterministic risk and data quality. The LLM may recommend, explain and flag contradictions, but it must not bypass the deterministic gate.

---

## Model and provider decision

### Primary model

```text
provider: Ollama Cloud compatible endpoint
primary_model: deepseek-v4-pro
temperature: 0.1
```

### Fallback model

```text
fallback_model: deepseek-v4-flash or another configured fast fallback model
temperature: 0.1
```

### Summary model / mode

For notification or context summaries only:

```text
summary_temperature: 0.15
```

### Why this split

- Signal evaluation should be deterministic and low-variance.
- Summaries can be slightly more natural, but still controlled.
- Fallback model is for availability and latency, not for independent authority.

---

## Recommended MVP configuration

```yaml
evaluation:
  enabled: true
  provider: ollama_cloud
  base_url_env: RAINBOW_LLM_BASE_URL
  api_key_env: RAINBOW_LLM_API_KEY
  primary_model: deepseek-v4-pro
  fallback_model: deepseek-v4-flash
  temperature: 0.1
  summary_temperature: 0.15
  timeout_seconds: 6.0
  threshold: 0.55
  cache_ttl_seconds: 300
  max_reviews_per_cycle: 10
  critic:
    enabled: false
    trigger_min_priority: high
    trigger_min_risk_score: 0.7
```

Notes:

- Keep secret values in environment variables only.
- Do not hardcode API keys.
- Do not log API keys, request auth headers or raw secret-bearing config.
- `threshold: 0.55` is recommended to reduce low-value LLM calls during MVP.

---

## Extended AIEvaluation target schema

```python
class AIEvaluation(BaseModel):
    ai_confidence: float
    ai_risk_score: float
    risk_level: Literal["low", "medium", "high"]
    market_regime: Literal["trending", "ranging", "volatile", "quiet"]
    signal_quality: Literal["strong", "usable", "weak", "contradictory"]
    recommended_handling: Literal[
        "store_only",
        "summary",
        "risk_summary",
        "review_required",
        "suppress",
    ]
    contradictions: list[str]
    missing_context: list[str]
    reasoning: str
    summary: str
    model_used: str
    evaluation_latency_ms: int
```

### Field intent

| Field | Purpose |
|---|---|
| `ai_confidence` | LLM confidence in its evaluation, not the same as signal confidence |
| `ai_risk_score` | LLM-estimated qualitative risk, separate from deterministic risk score |
| `risk_level` | Human-readable low/medium/high classification |
| `market_regime` | Regime interpretation from provided context |
| `signal_quality` | Overall usefulness of the signal as an intelligence item |
| `recommended_handling` | LLM recommendation, not final authority |
| `contradictions` | Conflicts between TA, sentiment, news, risk, data quality |
| `missing_context` | Data that would improve confidence |
| `reasoning` | Short factual rationale |
| `summary` | Compact downstream summary for UI/notification/context |

---

## Prompting strategy

### Evaluator role

The evaluator should be instructed to:

- analyze the provided signal objectively;
- prefer caution under degraded data quality;
- identify contradictions;
- identify missing context;
- explain why a signal is or is not useful;
- never suggest direct order placement;
- return valid JSON only.

### Evaluator output requirements

The API call should request structured JSON output where supported by the configured endpoint. The prompt must also explicitly demand JSON-only output.

Target response rules:

```text
- JSON only.
- No markdown.
- No prose outside JSON.
- Use only allowed enum values.
- Keep reasoning short and factual.
- If data quality is degraded, lower signal_quality or recommended_handling.
```

---

## Review policy / rule-based arbiter

The LLM should produce a recommendation, but a deterministic policy should decide final handling.

Example policy:

```python
if data_quality.status != "ok":
    final_handling = "review_required"
elif deterministic_risk_score >= 0.75:
    final_handling = "risk_summary"
elif llm.signal_quality == "contradictory":
    final_handling = "review_required"
elif llm.ai_confidence >= 0.7 and llm.recommended_handling in {"summary", "risk_summary"}:
    final_handling = llm.recommended_handling
else:
    final_handling = "store_only"
```

Required rule:

```text
Deterministic risk/data-quality gate has precedence over LLM recommendation.
```

---

## Optional critic layer

The critic should not be part of the first MVP runtime path by default. It should be designed but disabled initially.

### Trigger candidates

Run critic only when:

- priority is high;
- deterministic risk score is high;
- signal quality is contradictory;
- social/news signal conflicts with technical context;
- data quality is degraded but signal looks attractive;
- derivatives positioning is extreme.

### Critic output

```python
class CriticEvaluation(BaseModel):
    disagreement: bool
    downgrade_reason: str | None
    manipulation_risk: Literal["low", "medium", "high"]
    missing_context: list[str]
    final_review_label: Literal[
        "accept_summary",
        "downgrade_to_store_only",
        "risk_only",
        "review_required",
        "suppress",
    ]
    reasoning: str
    model_used: str
    evaluation_latency_ms: int
```

### Important rule

The critic is a reviewer, not an authority. The final arbiter remains deterministic.

---

## MVP implementation order

### Phase 1 — Provider/config hardening

Goal: make the existing evaluator explicitly compatible with Ollama Cloud + DeepSeek V4 Pro.

Tasks:

- Extend `EvaluationConfig` with provider/base URL/API-key env names.
- Add primary/fallback model fields.
- Keep `temperature=0.1` default.
- Add `summary_temperature=0.15`.
- Add `max_reviews_per_cycle`.
- Preserve backward compatibility where possible.

### Phase 2 — Structured evaluation schema

Goal: enrich `AIEvaluation` without turning it into a trading authority.

Tasks:

- Add `ai_risk_score`.
- Add `signal_quality`.
- Add `recommended_handling`.
- Add `contradictions`.
- Add `missing_context`.
- Add `summary`.
- Update tests.

### Phase 3 — JSON response hardening

Goal: make LLM output robust.

Tasks:

- Request JSON object response where endpoint supports it.
- Validate with Pydantic.
- Add fallback behavior for invalid JSON.
- Add tests for invalid JSON, missing fields, enum violations, timeout and fallback model.

### Phase 4 — Review policy / arbiter

Goal: separate LLM recommendation from final handling.

Tasks:

- Add `review_policy.py`.
- Implement deterministic final handling rules.
- Ensure data quality and deterministic risk override optimistic LLM recommendations.
- Add tests for degraded data, high risk, contradictory signal and strong signal.

### Phase 5 — Optional critic design

Goal: prepare but do not enable critic by default.

Tasks:

- Add `critic_evaluator.py` skeleton or planning-only docs.
- Add config section with `critic.enabled=false`.
- Add trigger policy tests if implementation is included.

### Phase 6 — Signal summaries

Goal: use LLM output to make signals understandable.

Tasks:

- Use `summary` from `AIEvaluation` for compact downstream output.
- Add summary formatting for notification/context endpoints.
- Keep summaries short, factual and source-aware.

---

## MVP definition of done

The LLM review MVP is complete when:

- DeepSeek V4 Pro via Ollama Cloud-compatible config is explicit.
- Existing Rainbow evaluation still works.
- Evaluation output includes quality, risk, contradictions, missing context and summary.
- Invalid/empty/slow LLM responses degrade gracefully.
- Rule-based review policy decides final handling.
- Deterministic risk/data-quality gate has precedence.
- No live order behavior is introduced.
- Tests cover config, schema, JSON parsing, fallback and review policy.

---

## Recommended issues

1. `P2: Configure Ollama Cloud DeepSeek V4 Pro for Rainbow LLM evaluation`
2. `P2: Extend AIEvaluation schema for structured signal review`
3. `P2: Harden LLM JSON output validation and fallback behavior`
4. `P3: Add rule-based LLM review policy and final handling arbiter`
5. `P3: Design optional critic evaluator for high-impact signal review`
6. `P3: Add LLM-powered compact signal summaries for notifications and context API`

---

## Safety constraints

- No automatic order placement.
- No live-exchange activation.
- No LLM-only high-priority decision.
- No secrets in logs or persisted evaluations.
- No raw private source payloads in summaries.
- LLM output is advisory and auditable.
