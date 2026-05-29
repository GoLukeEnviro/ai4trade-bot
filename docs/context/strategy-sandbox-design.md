# Strategy Sandbox -- Interface-Design

**Status:** Teilweise implementiert (Phase 1.2)
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- Strategie-Austausch und Sandbox

---

## 1. Uebersicht

Die Strategy-Komponente ist als austauschbares Interface designed. Die aktuelle `Strategy`-Klasse in `core/strategy.py` implementiert ein hybrides TA+Sentiment-Modell. Das Interface erlaubt kuenftige alternative Strategien ohne Aenderungen an der Pipeline.

---

## 2. Strategy-Interface

### Signatur

```python
def decide(self, ta: dict, sentiment: dict, pair: str, price: float, quantity: float) -> Signal
```

### Parameter

| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `ta` | `dict` | TA-Ergebnis mit `signal` (BUY/SELL/HOLD) und `strength` (0-100) |
| `sentiment` | `dict` | Sentiment mit `score` (-1.0 bis +1.0) |
| `pair` | `str` | Trading-Paar (z.B. `BTCUSDT`) |
| `price` | `float` | Aktueller Preis |
| `quantity` | `float` | Zu handelnde Menge |

### Rueckgabe

`Signal`-Objekt mit `pair`, `action`, `confidence`, `price`, `quantity`.

---

## 3. Aktuelle Implementierung

`core/strategy.py` -- HybridStrategy:

- TA-Signal bestimmt Richtung (BUY/SELL/HOLD)
- Sentiment modifiziert Confidence:
  - BUY: `confidence = strength * (1 + sentiment_score * 0.3)`
  - SELL: `confidence = strength * (1 - sentiment_score * 0.3)`
  - HOLD: bleibt HOLD, ignoriert Sentiment
- `sentiment_weight` konfigurierbar (Default: 0.3)

---

## 4. Zukuenftige Erweiterung

### Strategy Protocol

```python
class Strategy(Protocol):
    def decide(self, ta: dict, sentiment: dict, pair: str, price: float, quantity: float) -> Signal: ...
```

Formalisieren des aktuellen impliziten Interface als `typing.Protocol`.

### Strategy Registry

```python
# Zukuenftig: strategies/ Package
strategies/
    __init__.py
    hybrid.py      # Aktuelle Strategy
    momentum.py    # Beispiel: Momentum-Strategie
    meanrev.py     # Beispiel: Mean-Reversion
```

### Registry-Nutzung

```python
strategy = StrategyRegistry.get("hybrid")  # oder "momentum", etc.
signal = strategy.decide(ta, sentiment, pair, price, quantity)
```

---

## 5. Sandbox-Modus

- **Backtesting:** Historische OHLCV-Daten durch Strategy leiten (siehe `replay-engine-design.md`)
- **A/B-Vergleich:** Zwei Strategien parallel, Ergebnisse vergleichen
- **Keine Execution:** Sandbox-Ergebnisse werden geloggt aber nicht ausgefuehrt
- **Metriken:** Win-Rate, Sharpe-Ratio, Max-Drawdown pro Strategie

---

## 6. Constraints

- Strategy erhaelt nur Daten, keinen Zugriff auf Exchange oder Execution
- Strategy ist zustandslos (stateless) -- kein interner State zwischen Aufrufen
- Confidence immer [0, 100], Action immer BUY/SELL/HOLD

---

## 7. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Design-Dokumentation | 1.2 |
