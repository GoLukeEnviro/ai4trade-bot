# Zeitreihenanalyse & Prädiktive Modellierung für Finanz-Handelssysteme

> Deep-Dive Research-Dokument — Krypto & Gold Fokus
> Erstellt: 2026-06-06 | Projekt: ai4trade-bot

---

## Inhaltsverzeichnis

1. [Mathematische & Statistische Grundlagen](#1-mathematische--statistische-grundlagen)
2. [Vorhersagemethoden: Klassisch bis Deep Learning](#2-vorhersagemethoden)
3. [Krypto-Trading: Spezifische Anwendung](#3-krypto-trading)
4. [Gold-Trading: Spezifische Anwendung](#4-gold-trading)
5. [Signalgenerierung](#5-signalgenerierung)
6. [Backtesting & Performance-Evaluation](#6-backtesting--performance-evaluation)
7. [Risikomanagement & Robustheit](#7-risikomanagement--robustheit)
8. [Datenquellen, Feature-Engineering & Vorverarbeitung](#8-datenquellen-feature-engineering--vorverarbeitung)
9. [Echtzeit-Implementierung & Deployment](#9-echtzeit-implementierung--deployment)
10. [Bewertungsmatrix & Empfehlungen](#10-bewertungsmatrix--empfehlungen)
11. [Architektur-Blueprint für ai4trade-bot](#11-architektur-blueprint-für-ai4trade-bot)
12. [Quellen & Referenzen](#12-quellen--referenzen)

---

## 1. Mathematische & Statistische Grundlagen

### 1.1 ARIMA (AutoRegressive Integrated Moving Average)

**Mathematische Formulierung:**

Ein ARIMA(p, d, q)-Modell kombiniert drei Komponenten:

- **AR(p) — Autoregression:** `X_t = c + Σ(φ_i · X_{t-i}) + ε_t` für i=1..p
- **I(d) — Integration (Differencing):** `Y_t = X_t - X_{t-1}` (d-mal differenzieren bis stationär)
- **MA(q) — Moving Average:** `X_t = μ + ε_t + Σ(θ_i · ε_{t-i})` für i=1..q

**Kombiniert:**
```
X_t = c + φ_1·X_{t-1} + ... + φ_p·X_{t-p} + ε_t + θ_1·ε_{t-1} + ... + θ_q·ε_{t-q}
```

**Eignung für Finanzdaten:**
- Gut für **stationäre** Zeitreihen nach Differencing
- ADF-Test (Augmented Dickey-Fuller) zur Prüfung der Stationarität
- **Einschränkung:** Kann keine Volatilitätsclusterung modellieren — wichtig bei Krypto!
- Typische Parameter für Krypto: ARIMA(1,1,1) bis ARIMA(5,1,2)
- **Auto-ARIMA** (pmdarima) automatisiert Parameterwahl via AIC/BIC

**Code-Skizze:**
```python
from pmdarima import auto_arima
from statsmodels.tsa.arima.model import ARIMA

# Auto-ARIMA mit automatischer Parametersuche
model = auto_arima(
    prices, start_p=1, start_q=1, max_p=5, max_q=5,
    d=1, seasonal=False, stepwise=True,
    information_criterion='aic', trace=True
)

# Vorhersage
forecast, conf_int = model.predict(n_periods=24, return_conf_int=True)
```

**Bewertung:** Mittelmäßige Eignung für Krypto alleinstehend. Nützlich als Baseline und in Kombination mit GARCH für Volatilität.

---

### 1.2 GARCH (Generalized Autoregressive Conditional Heteroskedasticity)

**Mathematische Formulierung:**

GARCH(p, q) modelliert die bedingte Varianz:

```
σ²_t = ω + Σ(α_i · ε²_{t-i}) + Σ(β_j · σ²_{t-j})

wobei:
  ε_t = σ_t · z_t,  z_t ~ N(0,1)
  ω > 0, α_i ≥ 0, β_j ≥ 0
  Σ(α_i + β_j) < 1  (Stationaritätsbedingung)
```

**GARCH(1,1) — der De-facto-Standard:**
```
σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}
```

**Erweiterungen:**
- **EGARCH:** Modelliert asymmetrische Effekte (Leverage-Effekt: negative Schocks → höhere Volatilität)
- **GJR-GARCH:** Indikatorfunktion für negative Returns
- **APARCH:** Flexible Power-Parametrisierung
- **TGARCH:** Threshold-GARCH für Regime-Wechsel

**Warum essenziell für Krypto:**
- Krypto zeigt extrem ausgeprägte Volatilitätsclusterung
- GARCH fängt "Fat Tails" und "Volatility Clustering" ab
- Kombination ARIMA + GARCH = Prognose für Mittelwert UND Unsicherheit

**Code-Skizze:**
```python
from arch import arch_model

# GARCH(1,1) mit Student-t Innovationen (besser für Fat Tails)
returns = np.log(prices / prices.shift(1)).dropna() * 100

model = arch_model(returns, vol='Garch', p=1, q=1,
                   dist='StudentsT', mean='AR', lags=1)
result = model.fit(disp='off')

# Volatilitätsprognose
forecast = result.forecast(horizon=24)
vol_forecast = np.sqrt(forecast.variance.values[-1, :])
```

**Bewertung:** HOHE Eignung. Zwingend notwendig für jedes Krypto-System. Liefert Volatilitätsbänder für Stop-Loss und Positionsgrößen.

---

### 1.3 Exponentielle Glättung (ETS — Error, Trend, Seasonality)

**Mathematische Formulierung:**

**Simple Exponential Smoothing (SES):**
```
l_t = α · y_t + (1-α) · l_{t-1}    (Level)
```

**Holt's Linear Trend:**
```
l_t = α · y_t + (1-α) · (l_{t-1} + b_{t-1})    (Level)
b_t = β · (l_t - l_{t-1}) + (1-β) · b_{t-1}     (Trend)
```

**Holt-Winters (additiv/multiplikativ):**
```
l_t = α · (y_t - s_{t-m}) + (1-α) · (l_{t-1} + b_{t-1})
b_t = β · (l_t - l_{t-1}) + (1-β) · b_{t-1}
s_t = γ · (y_t - l_t) + (1-γ) · s_{t-m}
ŷ_{t+h} = l_t + h·b_t + s_{t+h-m}
```

**Eignung für Finanzdaten:**
- Krypto hat **keine verlässliche Saisonalität** (24/7-Markt), aber:
- **Intraday-Patterns** existieren ( asiatische / europäische / US-Session)
- **Wöchentliche Zyklen** sind teilweise beobachtbar
- Holt-Winters für **Trend-Extraktion** nutzbar
- **ETS-Zerlegung** für Feature-Engineering: Trend + Saison + Residuum

**Code-Skizze:**
```python
from statsmodels.tsa.holtwinters import ExponentialSmoothing

model = ExponentialSmoothing(
    prices, trend='add', seasonal=None,
    initialization_method='estimated'
).fit(smoothing_level=0.2)

forecast = model.forecast(24)
```

**Bewertung:** Niedrige bis mittlere Eignung für direkte Prognose. Wertvoll für Trend-Extraktion und als Feature für ML-Modelle.

---

### 1.4 Zustandsraummodelle (State Space Models)

**Mathematische Formulierung:**

```
Zustandsgleichung:   α_t = T_t · α_{t-1} + R_t · η_t,  η_t ~ N(0, Q_t)
Beobachtungsgleichung: y_t = Z_t · α_t + ε_t,  ε_t ~ N(0, H_t)
```

**Wichtige Instanziierungen:**

**Kalman-Filter:**
- Rekursiver Optimalfilter für lineare Zustandsraummodelle
- Liefert: gefilterte Zustände + Konfidenzintervalle in Echtzeit
- Ideal für Online-Updates (eine Beobachtung nach der anderen)

**Structural Time Series (STS):**
```
y_t = μ_t + τ_t + ε_t

μ_t = μ_{t-1} + ν_{t-1} + ξ_t     (Local Linear Trend)
ν_t = ν_{t-1} + ζ_t
τ_t = -Σ(τ_{t-j}) + ω_t            (Saisonale Komponente, j=1..s-1)
```

**Eignung für Finanzdaten:**
- **Adaptive Parameterschätzung** — Modell passt sich an Regime-Wechsel an
- **Online-Learning** — perfekt für Echtzeit-Streaming
- **Konfidenzintervalle** natürlich integriert
- Kombinierbar mit beliebigen Beobachtungsgleichungen

**Code-Skizze:**
```python
import statsmodels.api as sm

# Unobserved Components Model
model = sm.tsa.UnobservedComponents(
    prices, level='local level', trend=True,
    seasonal=24, stochastic_seasonal=True
)
result = model.fit()

# Kalman-Filter Online-Update
filtered = result.filtered_state
forecast = result.predict(start=len(prices), end=len(prices)+24)
```

**Bewertung:** HOHE Eignung. Besonders wertvoll für Echtzeit-Anwendungen mit sich ändernden Marktbedingungen. Unterrepräsentiert in Trading-Systemen.

---

### 1.5 Weitere Grundlagenmodelle

**VAR (Vector Autoregression):**
- Multivariat: Modelliert gegenseitige Abhängigkeiten zwischen mehreren Zeitreihen
- Anwendbar: BTC & ETH & SOL gleichzeitig, oder Krypto & Gold & DXY
- `Y_t = A_1·Y_{t-1} + ... + A_p·Y_{t-p} + u_t`

**Regime-Switching-Modelle (Markov-Switching):**
- Mehrere Zustände (z.B. Bull/Bear/Sideways)
- Übergangswahrscheinlichkeiten zwischen Zuständen
-非常适合 für Krypto-Marktphasen-Erkennung

**Wavelet-Zerlegung:**
- Zerlegung in Frequenzbänder — Trend/Rauschen-Trennung
- MODWT (Maximal Overlap DWT) für Finanzdaten bevorzugt
- Nützlich als Preprocessing-Schritt für ML-Modelle

---

## 2. Vorhersagemethoden: Klassisch bis Deep Learning

### 2.1 Modell-Landschaft — Übersicht

```
                    ┌─────────────────────────────────────────┐
                    │         Vorhersagemethoden               │
                    └─────────────┬───────────────────────────┘
                                  │
            ┌─────────────────────┼──────────────────────┐
            │                     │                      │
    ┌───────▼──────┐    ┌────────▼──────┐    ┌──────────▼──────┐
    │  Klassisch    │    │  Machine       │    │  Deep Learning   │
    │  Statistisch  │    │  Learning      │    │                  │
    └───────┬──────┘    └────────┬──────┘    └──────────┬──────┘
            │                    │                       │
    ARIMA           Random Forest            LSTM
    GARCH           XGBoost/GBRT             GRU
    ETS             LightGBM                 Transformer
    VAR             SVM                      Temporal ConvNet
    State Space     Bayesian Ridge           Hybrid (LSTM+Transformer)
    Kalman          Elastic Net              N-BEATS
    Markov Switch   CatBoost                 N-HiTS
            │                    │                       │
            └─────────────────────┼──────────────────────┘
                                  │
                    ┌─────────────▼───────────────────────┐
                    │     Reinforcement Learning           │
                    │  DQN · PPO · A2C · DDPG · SAC       │
                    └─────────────────────────────────────┘
```

### 2.2 Machine-Learning-Ansätze

#### 2.2.1 Gradient Boosting (XGBoost / LightGBM / CatBoost)

**Warum besonders relevant:**
- Tabellarische Finanzdaten → GBM-dominiert oft gegen DL
- Schnelles Training, interpretierbar (Feature Importance)
- Robust gegen Overfitting mit Regularisierung

**Feature-Engineering ist der Schlüssel:**
```python
# Typische Feature-Sets für Krypto
features = {
    'price_features': [
        'return_1h', 'return_4h', 'return_24h', 'return_7d',
        'log_return', 'cumulative_return_5d'
    ],
    'technical_indicators': [
        'rsi_14', 'macd', 'macd_signal', 'macd_hist',
        'bb_upper', 'bb_lower', 'bb_pct', 'bb_width',
        'ema_20', 'ema_50', 'ema_200', 'sma_cross',
        'atr_14', 'adx_14', 'cci_20', 'williams_r',
        'stoch_k', 'stoch_d', 'obv', 'vwap'
    ],
    'volatility_features': [
        'realized_vol_1h', 'realized_vol_24h',
        'garman_klass_vol', 'parkinson_vol',
        'vol_ratio_short_long', 'vol_skew'
    ],
    'volume_features': [
        'volume_sma_ratio', 'volume_std',
        'dollar_volume', 'tick_volume_ratio'
    ],
    'microstructure': [
        'bid_ask_spread', 'order_imbalance',
        'trade_intensity', 'vwap_deviation'
    ]
}
```

**Bewertung:** HOHE Eignung als primäres Modell. Besonders XGBoost und LightGBM dominieren Kaggle-Wettbewerbe für Finanzvorhersagen.

#### 2.2.2 LSTM (Long Short-Term Memory)

**Architektur für Finanzzeitreihen:**

```
Input: [batch, seq_len, features]
       ↓
┌──────────────────────────┐
│  LSTM Layer 1 (128 units)│ → return_sequences=True
│  Dropout (0.2)           │
├──────────────────────────┤
│  LSTM Layer 2 (64 units) │ → return_sequences=True
│  Dropout (0.2)           │
├──────────────────────────┤
│  LSTM Layer 3 (32 units) │ → return_sequences=False
│  Dropout (0.2)           │
├──────────────────────────┤
│  Dense (16, ReLU)        │
│  BatchNorm               │
│  Dense (1, Linear)       │  ← Prognose
└──────────────────────────┘

Output: [batch, forecast_horizon]
```

**Code-Skizze:**
```python
import torch
import torch.nn as nn

class CryptoLSTM(nn.Module):
    def __init__(self, input_dim, hidden_dim=128, num_layers=3, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers,
                           batch_first=True, dropout=dropout)
        self.bn = nn.BatchNorm1d(hidden_dim)
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 1)
        )

    def forward(self, x):
        # x: [batch, seq_len, features]
        lstm_out, (h_n, c_n) = self.lstm(x)
        out = self.bn(h_n[-1])  # Letzter Hidden-State
        return self.fc(out)
```

**Hyperparameter-Empfehlungen für Krypto:**
- Sequenzlänge: 48-168 (2-7 Tage bei stündlichen Daten)
- Hidden Units: 64-256
- Layers: 2-3 (mehr → Overfitting-Gefahr)
- Dropout: 0.2-0.3
- Learning Rate: 1e-3 mit CosineAnnealing
- Batch Size: 32-64

**Bewertung:** HOHE Eignung für Trendfolge. Gut darin, zeitliche Abhängigkeiten zu lernen. Gefahr von Overfitting bei kleinen Datensätzen.

> **Wichtiger Hinweis — Async-Constraint:** PyTorch/LSTM sind **synchron** und blockieren den asyncio Event Loop des ai4trade-bot. Für den produktiven Einsatz gibt es zwei Optionen:
> 1. **ONNX Runtime Export:** `torch.onnx.export()` → ONNX-Modell → `onnxruntime.InferenceSession` (async-kompatibel via `loop.run_in_executor`)
> 2. **Separater Model-Server:** Eigenständiger ONNX/Triton-Server, der via HTTP/gRPC vom Bot aufgerufen wird
>
> Niemals `model.forward()` direkt im async Main-Loop aufrufen — das friert die WebSocket-Verbindung ein.

#### 2.2.3 Transformer für Finanzzeitreihen

**Warum Transformer relevant sind:**
- **Self-Attention** kann langfristige Abhängigkeiten erfassen
- Parallelisierbar (schnelleres Training als LSTM)
- **Informert** (2021): Speziell für Zeitreihen entwickelt
- **PatchTST** (2023): Patch-basiert, State-of-the-Art
- **Temporal Fusion Transformer (TFT)**: Interpretierbar mit Variable Selection

**Temporal Fusion Transformer — Architektur:**
```
┌─────────────────────────────────────────────────┐
│  Input Layer                                     │
│  ├─ Known Future Inputs (z.B. geplante Events)   │
│  ├─ Observed Inputs (Preise, Volumen)            │
│  └─ Static Covariates (Asset-Charakteristika)    │
├─────────────────────────────────────────────────┤
│  Variable Selection Network                      │
│  → Gewichtet Features dynamisch pro Zeitschritt  │
├─────────────────────────────────────────────────┤
│  LSTM Encoder-Decoder                            │
│  → Lokale zeitliche Abhängigkeiten               │
├─────────────────────────────────────────────────┤
│  Multi-Head Attention                            │
│  → Langfristige Abhängigkeiten                   │
├─────────────────────────────────────────────────┤
│  Quantile Output                                 │
│  → P10, P50, P90 Prognosen mit Unsicherheit      │
└─────────────────────────────────────────────────┘
```

**Code-Skizze (PyTorch Forecasting):**
```python
from pytorch_forecasting import TemporalFusionTransformer

tft = TemporalFusionTransformer.from_dataset(
    training_dataset,
    learning_rate=1e-3,
    hidden_size=64,
    attention_head_size=4,
    dropout=0.1,
    hidden_continuous_size=32,
    output_size=7,  # 7 Quantile
    loss=QuantileLoss(),
    log_interval=10,
    reduce_on_plateau_patience=4,
)
```

**Bewertung:** SEHR HOHE Eignung. TFT liefert interpretierbare Ergebnisse + Quantilsprognosen. State-of-the-Art für multivariate Finanzzeitreihen.

#### 2.2.4 Reinforcement Learning (RL) für Trading

> **Einordnung: Langfristige Perspektive (>12 Monate)**
> RL ist **kein** Kandidat für die ersten Implementierungsphasen. Erforderliche Voraussetzungen:
> - Mindestens 2+ Jahre saubere historische Daten pro Asset
> - Ein stabiles Basis-Modell als Reward-Signal-Quelle (z.B. XGBoost-Ensemble)
> - Hunderte Stunden Simulationszeit für ausreichende Exploration
> - Getestete und validierte Backtesting-Infrastruktur
>
> **Ohne diese Grundlage ist RL pures Overfitting auf historische Daten.**

**Warum RL für Trading relevant:**
- Lernt **Aktionsstrategien** (Buy/Sell/Hold), nicht nur Preisvorhersagen
- Berücksichtigt Transaktionskosten, Slippage, Marktimpact
- **Sequential Decision Making** unter Unsicherheit

**Algorithmen-Landschaft:**

| Algorithmus | Aktionsraum | Stärken | Trading-Einsatz |
|---|---|---|---|
| DQN | Diskret | Einfach, stabil | Buy/Sell/Hold |
| PPO | Kontinuierlich | Stabil, sample-effizient | Positionsgrößen |
| A2C/A3C | Beide | Parallelisierbar | Multi-Asset |
| DDPG | Kontinuierlich | Deterministisch | Portfolio-Gewichte |
| SAC | Kontinuierlich | Exploration, robust | Portfolio-Optimierung |

**RL-Umgebung für Krypto-Trading:**
```python
import gymnasium as gym
from gymnasium import spaces
import numpy as np

class CryptoTradingEnv(gym.Env):
    def __init__(self, df, initial_balance=10000):
        super().__init__()
        self.df = df
        self.balance = initial_balance
        self.position = 0

        # Observation: [price_features, portfolio_state, market_state]
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(len(df.columns) + 3,), dtype=np.float32
        )
        # Action: 0=Hold, 1=Buy, 2=Sell
        self.action_space = spaces.Discrete(3)

    def step(self, action):
        current_price = self.df.iloc[self.current_step]['close']

        if action == 1 and self.position == 0:  # Buy
            self.position = self.balance / current_price
            self.balance = 0
        elif action == 2 and self.position > 0:  # Sell
            self.balance = self.position * current_price
            self.position = 0

        self.current_step += 1
        portfolio_value = self.balance + self.position * current_price

        reward = (portfolio_value - self.prev_value) / self.prev_value
        self.prev_value = portfolio_value

        done = self.current_step >= len(self.df) - 1
        obs = self._get_observation()

        return obs, reward, done, False, {}

    def reset(self, seed=None):
        self.current_step = 0
        self.balance = 10000
        self.position = 0
        self.prev_value = 10000
        return self._get_observation(), {}
```

**FinRL — Production-ready Framework:**
```python
from finrl import config
from finrl.agents.stablebaselines3.models import DRLAgent

agent = DRLAgent(env=env)
model = agent.get_model("PPO", model_kwargs={
    'learning_rate': 3e-4,
    'n_steps': 2048,
    'batch_size': 128,
    'ent_coef': 0.01,
})
trained = agent.train_model(model, total_timesteps=100000)
```

**Bewertung:** HOHE Eignung für Portfolio-Optimierung. Komplexe Implementierung. Kombinierbar mit prädiktiven Modellen als "Meta-Controller".

---

### 2.3 Ensemble- und Hybrid-Strategien

**Warum Ensembles dominieren:**
- Einzelmodelle haben systematische Schwächen
- Kombination verschiedener Modelltypen → robustere Prognosen
- Empirisch nachgewiesen: Ensembles übertreffen Einzelmodelle konsistent

**Bewährte Ensemble-Patterns:**

```
┌─────────────────────────────────────────────────┐
│              Ensemble-Architektur                │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  ARIMA   │  │  LSTM    │  │ XGBoost  │      │
│  │ + GARCH  │  │  Encoder │  │  Regr.   │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │              │             │             │
│       ▼              ▼             ▼             │
│  [Prognose_1]  [Prognose_2]  [Prognose_3]       │
│       │              │             │             │
│       └──────────────┼─────────────┘             │
│                      ▼                           │
│            ┌─────────────────┐                   │
│            │ Meta-Learner    │                   │
│            │ (Stacking/      │                   │
│            │  Weighted Avg)  │                   │
│            └────────┬────────┘                   │
│                     ▼                            │
│            [Finale Prognose]                      │
│            [Konfidenz-Score]                      │
└─────────────────────────────────────────────────┘
```

**Code-Skizze — Weighted Ensemble:**
```python
class TradingEnsemble:
    def __init__(self):
        self.models = {
            'arima': ARIMAModel(),
            'lstm': LSTMModel(),
            'xgboost': XGBoostModel(),
            'tft': TFTModel(),
        }
        # Performance-basierte Gewichte (periodisch aktualisiert)
        self.weights = {'arima': 0.15, 'lstm': 0.30,
                       'xgboost': 0.30, 'tft': 0.25}

    def predict(self, features):
        predictions = {}
        confidences = {}
        for name, model in self.models.items():
            pred, conf = model.predict(features)
            predictions[name] = pred
            confidences[name] = conf

        # Gewichtete Prognose
        ensemble_pred = sum(
            self.weights[n] * predictions[n] * confidences[n]
            for n in self.models
        )
        ensemble_conf = np.mean(list(confidences.values()))

        return ensemble_pred, ensemble_conf
```

---

## 3. Krypto-Trading: Spezifische Anwendung

### 3.1 Marktcharakteristika

| Eigenschaft | Krypto-Märkte | Traditionelle Märkte |
|---|---|---|
| Handelszeiten | 24/7/365 | Börsenöffnungszeiten |
| Volatilität | Extrem hoch (Jahresvol. 60-100%) | Moderat (Jahresvol. 15-25%) |
| Liquidität | Fragmentiert, variabel | Hoch, zentralisiert |
| Fat Tails | Sehr ausgeprägt | Vorhanden, moderat |
| Marktreaktion | Minuten | Minuten bis Stunden |
| Regulierung | Minimal bis moderat | Streng |
| Korrelation | Hohe Inter-Krypto-Korrelation | Sektorspezifisch |
| Manipulation | Höheres Risiko | Reguliert |

### 3.2 Volatilitätsmodellierung für Krypto

**Realized Volatility (RV) — Multiple Estimators:**

```python
def garman_klass_vol(o, h, l, c):
    """Garman-Klass Volatilitätsschätzer"""
    return np.sqrt(
        0.5 * np.log(h / l) ** 2 -
        (2 * np.log(2) - 1) * np.log(c / o) ** 2
    )

def parkinson_vol(h, l):
    """Parkinson Volatilitätsschätzer"""
    return np.sqrt(
        (1 / (4 * np.log(2))) * np.log(h / l) ** 2
    )

def realized_vol(returns):
    """Standard Realized Volatility"""
    return np.sqrt(np.sum(returns ** 2))
```

**HAR-RV (Heterogeneous Autoregressive Realized Volatility):**
```
RV_t+1d = β_0 + β_d·RV_t + β_w·RV_t^(5d) + β_m·RV_t^(22d) + ε_t
```
- Berücksichtigt unterschiedliche Zeithorizonte (daily, weekly, monthly)
- Empirisch: HAR-RV + Sentiment outperformed reine HAR-RV signifikant

### 3.3 Sentiment-Analyse

**Datenquellen für Krypto-Sentiment:**
- **Social Media:** Twitter/X, Reddit (r/cryptocurrency, r/bitcoin)
- **News:** CryptoCompare, CoinDesk, Cointelegraph
- **On-Chain:** Glassnode, CryptoQuant, Santiment
- **Fear & Greed Index:** Alternative.me
- **Liquidation-Data:** Coinglass, Bybit

**Sentiment-Pipeline:**
```
Rohdaten → Preprocessing → Feature-Extraction → Sentiment-Score

┌────────────┐    ┌──────────────┐    ┌───────────────┐
│ News API   │───→│ NLP Pipeline │───→│ Sentiment     │
│ Reddit API │    │ (FinBERT /   │    │ Score [-1, 1] │
│ Twitter API│    │  LLM)        │    │ + Confidence  │
└────────────┘    └──────────────┘    └───────────────┘
```

**On-Chain-Metriken als Features:**
```python
on_chain_features = {
    'active_addresses': 'Täglich aktive Adressen',
    'exchange_inflow': 'BTC/ETH Fluss zu Börsen (bärisch)',
    'exchange_outflow': 'BTC/ETH Abfluss von Börsen (bullish)',
    'whale_transactions': 'Großtransaktionen > $1M',
    'miners_reserve': 'Miner-Bestände (Selling Pressure)',
    'stablecoin_supply': 'USDT/USDC Supply (Kaufkraft)',
    'funding_rate': 'Perp-Funding (Long/Short Balance)',
    'open_interest': 'Offene Kontrakte',
    'liquidation_levels': 'Liquidations-Clustern',
    'mvrv_ratio': 'Market Value to Realized Value',
    'nupl': 'Net Unrealized Profit/Loss',
}
```

### 3.4 24/7-Markt — Besonderheiten

**Intraday-Patterns:**
```
UTC-Zeit    Volumen/Volatilität    dominanter Markt
───────────────────────────────────────────────────
00:00-04:00  Niedrig               Asien (Japan/Korea)
04:00-08:00  Steigend              Asien → Europa
08:00-12:00  Mittel-Hoch           Europa
12:00-16:00  Hoch                  Europa + US Vormittag
16:00-20:00  Höchster              US (Wall Street)
20:00-22:00  Sinkend               US Nachmittag
22:00-00:00  Niedrig               Übergang Asien
```

**Feature für Zeit-basierte Effekte:**
```python
def time_features(timestamp_utc):
    hour = timestamp_utc.hour
    return {
        'hour_sin': np.sin(2 * np.pi * hour / 24),
        'hour_cos': np.cos(2 * np.pi * hour / 24),
        'is_weekend': timestamp_utc.weekday() >= 5,
        'is_asia_session': 0 <= hour < 8,
        'is_europe_session': 8 <= hour < 16,
        'is_us_session': 16 <= hour < 24,
        'session_overlap_eu_us': 16 <= hour < 20,  # Höchste Liquidität
    }
```

---

## 4. Gold-Trading: Spezifische Anwendung

### 4.1 Makroökonomische Einflussfaktoren

**Primäre Treiber des Goldpreises:**

```
                    ┌──────────────────┐
                    │   GOLDPREIS      │
                    └────────┬─────────┘
                             │
        ┌────────────┬───────┼────────┬────────────┐
        │            │       │        │            │
   ┌────▼────┐ ┌────▼───┐ ┌▼──────┐ ┌▼─────────┐ ┌▼──────────┐
   │ USD/DXY │ │Real-   │ │Zinsen │ │Geopolitik│ │Zentral-   │
   │ Stärke  │ │zinsen  │ │(Yields│ │Risiko    │ │bankkäufe  │
   │         │ │(TIPS)  │ │)      │ │          │ │            │
   └─────────┘ └────────┘ └───────┘ └──────────┘ └───────────┘
        │            │         │          │            │
   Neg. Korr    Neg. Korr  Neg. Korr  Pos. Korr   Pos. Korr
   (~-0.85)     (~-0.75)   (~-0.70)   (Krise↑)    (Demand↑)
```

**Quantitative Beziehungen:**

| Faktor | Korrelation | Lag | Beschreibung |
|---|---|---|---|
| DXY (USD Index) | -0.80 bis -0.90 | 0-2 Tage | Stärkster inverser Treiber |
| US 10Y Yields | -0.60 bis -0.75 | 1-3 Tage | Opportunitätskosten |
| Real Yields (TIPS) | -0.70 bis -0.85 | 0-2 Tage | Inflationsbereinigt |
| CPI/Inflation | +0.40 bis +0.60 | 1-4 Wochen | Inflationshedge |
| VIX | +0.30 bis +0.50 | 0-1 Tag | Risiko-Aversion |
| SPX | -0.30 bis -0.50 | 0-3 Tage | Flucht aus Aktien |

### 4.2 Gold-Vorhersagemodelle

**Feature-Set für Gold:**
```python
gold_features = {
    'price_technical': [
        'gold_return_1d', 'gold_return_5d', 'gold_return_20d',
        'gold_rsi_14', 'gold_macd', 'gold_ema_50_200_ratio',
        'gold_bollinger_pct', 'gold_atr_14',
    ],
    'forex': [
        'dxy_level', 'dxy_return_1d', 'dxy_return_5d',
        'eur_usd', 'usd_jpy', 'usd_chf',
    ],
    'rates': [
        'us_10y_yield', 'us_2y_yield', 'yield_curve_spread',
        'real_yield_10y', 'fed_funds_rate',
        'yield_change_1d', 'yield_change_5d',
    ],
    'inflation': [
        'cpi_yoy', 'core_cpi_yoy', 'pce_yoy',
        'inflation_expectation_5y', 'breakeven_10y',
    ],
    'risk_sentiment': [
        'vix_level', 'vix_change_1d',
        'spx_return_1d', 'spx_return_5d',
        'credit_spread_baa_aaa', 'ted_spread',
    ],
    'flows': [
        'gold_etf_flow_gld', 'gold_etf_flow_iau',
        'cftc_managed_net_long', 'cftc_commercial_net',
        'central_bank_gold_reserves_change',
    ],
    'macro': [
        'gdp_growth_qoq', 'unemployment_rate',
        'pmi_manufacturing', 'consumer_confidence',
        'retail_sales_mom',
    ],
}
```

**Hybrid-Modell für Gold:**
```python
class GoldPredictor:
    """
    Hybrid: Macro-Fundamental + Technisch + ML
    1. Fundamental: Regime-basierte Gewichtung basierend auf Makro-Umfeld
    2. Technisch: Trend/Modell-basierte Signale
    3. ML: XGBoost/LSTM für residuale Prognose
    """
    def __init__(self):
        self.macro_regime = MacroRegimeDetector()  # HMM
        self.tech_model = TechnicalAnalyzer()
        self.ml_model = XGBRegressor(...)

    def predict(self, features):
        # 1. Makro-Regime erkennen (Risk-On/Risk-Off/Neutral)
        regime = self.macro_regime.detect(features)
        regime_weight = {'risk_off': 0.5, 'risk_on': 0.2, 'neutral': 0.3}

        # 2. Technische Signale
        tech_signal = self.tech_model.analyze(features)

        # 3. ML-Prognose
        ml_forecast = self.ml_model.predict(features)

        # 4. Regime-gewichtete Kombination
        final = (regime_weight[regime] * ml_forecast +
                (1 - regime_weight[regime]) * tech_signal)

        return final, regime
```

### 4.3 Safe-Haven-Dynamik

**Gold als Safe-Haven — Quantitative Eigenschaften:**

1. **Negative Korrelation mit riskanten Assets während Krisen:**
   - Korrelation SPX-Gold: Normal ~-0.30, Krise ~-0.60 bis -0.80
   - Korrelation Krypto-Gold: Schwach (~+0.10 bis +0.20), steigt in Krisen

2. **Asymmetrische Response:**
   - Große negative Equity-Returns → Überproportionaler Gold-Anstieg
   - Normale Tage → Schwache/keine Korrelation

3. **Zentralbank-Verhalten als Leading Indicator:**
   - Netto-Käufe von Zentralbanken → langfristig bullish
   - 2022-2025: Rekordkäufe (besonders China, Indien, Türkei)

---

## 5. Signalgenerierung

### 5.1 Architektur der Signal-Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                    SIGNAL-PIPELINE                            │
│                                                              │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │  Market  │──→│ Feature  │──→│  Model   │──→│  Signal  │ │
│  │  Data    │   │ Engine   │   │  Engine  │   │  Router  │ │
│  │  Feed    │   │          │   │          │   │          │ │
│  └─────────┘   └──────────┘   └──────────┘   └──────────┘ │
│       │              │              │              │          │
│  OHLCV + OB     Indikatoren    Ensemble-      Entry/Exit    │
│  Tick-Data      + ML-Features  Prognosen      + Risk-Params  │
│  Sentiment      + Makro-Data   + Konfidenz    + Sizing      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Entry-Signale

**Multi-Condition Entry (Konfluenz-basiert):**
```python
@dataclass
class EntrySignal:
    direction: str  # 'long' | 'short'
    confidence: float  # 0.0 - 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    signal_source: str  # welches Modell
    conditions_met: list  # erfüllte Bedingungen

class SignalGenerator:
    def __init__(self, config):
        self.min_conditions = config['min_conditions']  # z.B. 3 von 5

    def evaluate_entry(self, data, predictions):
        conditions = {
            'trend_alignment': self._check_trend(predictions),
            'momentum_confirmation': self._check_momentum(data),
            'volatility_regime': self._check_volatility(data),
            'sentiment_aligned': self._check_sentiment(predictions),
            'support_resistance': self._check_levels(data),
            'volume_confirmation': self._check_volume(data),
        }

        met = [k for k, v in conditions.items() if v]
        if len(met) < self.min_conditions:
            return None  # Nicht genug Konfluenz

        direction = predictions['direction']
        confidence = len(met) / len(conditions)

        return EntrySignal(
            direction=direction,
            confidence=confidence,
            entry_price=data['close'][-1],
            stop_loss=self._calc_stop_loss(data, direction),
            take_profit=self._calc_take_profit(data, direction),
            position_size=self._calc_position_size(confidence),
            signal_source='ensemble',
            conditions_met=met,
        )
```

### 5.3 Stop-Loss-Strategien

| Strategie | Formel | Einsatzgebiet |
|---|---|---|
| ATR-basiert | `SL = Entry ± N × ATR(14)` | Standard (N=1.5-2.0) |
| Volatilität-basiert | `SL = Entry ± σ × √T` | GARCH-Modell |
| Trailing Stop | `SL = max(High - N×ATR, prev_SL)` | Trendfolge |
| Chandelier Exit | `SL = High - N×ATR` (nur Long) | Swing-Trading |
| Keltner Channel | `SL = EMA ± N×ATR` | Range-Trading |
| Time-based | Close wenn nach N Bars im Verlust | Intraday |
| Kelly-adjusted | `SL = Entry - f×Capital/w` | Position-Sizing-konsistent |

### 5.4 Positionsgrößenbestimmung

**Kelly-Kriterium:**
```
f* = (p × b - q) / b

wobei:
  f* = Anteil des Kapitals
  p  = Wahrscheinlichkeit des Gewinns
  q  = 1 - p (Wahrscheinlichkeit des Verlusts)
  b  = Gewinn/Verlust-Verhältnis (Reward/Risk)
```

**Fractional Kelly (empfohlen für Praxis):**
```python
def fractional_kelly(win_rate, avg_win, avg_loss, fraction=0.25):
    """Fractional Kelly — 25% Kelly reduziert Volatilität drastisch"""
    b = avg_win / avg_loss
    p = win_rate
    q = 1 - p

    kelly_full = (p * b - q) / b
    kelly_frac = kelly_full * fraction

    return max(0, min(kelly_frac, 0.10))  # Cap bei 10% pro Trade
```

**Risk-Parity Sizing:**
```python
def risk_parity_size(capital, atr, target_vol=0.01):
    """Positionsgröße basierend auf Asset-Volatilität"""
    risk_per_unit = atr  # ATR als Risikoproxy
    position_size = (capital * target_vol) / risk_per_unit
    return position_size
```

---

## 6. Backtesting & Performance-Evaluation

### 6.1 Backtesting-Framework

**Backtest-Architektur:**
```
┌────────────────────────────────────────────────────────┐
│                  BACKTESTING ENGINE                     │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ Historic  │→ │ Strategy │→ │ Execution│→ Results    │
│  │ Data Feed │  │ Engine   │  │ Simulator│             │
│  └──────────┘  └──────────┘  └──────────┘            │
│       │              │              │                    │
│  Real OHLCV    Signal-Gen     Slippage                │
│  + Bid/Ask     + Risk-Mgmt    + Commission             │
│  + Volume      + Sizing       + Market Impact          │
└────────────────────────────────────────────────────────┘
```

**Code-Skizze — Vectorized Backtest:**
```python
class VectorizedBacktest:
    def __init__(self, data, strategy, initial_capital=10000):
        self.data = data
        self.strategy = strategy
        self.capital = initial_capital

    def run(self):
        results = []
        position = 0
        capital = self.capital

        for i in range(len(self.data)):
            signal = self.strategy.generate_signal(self.data.iloc[:i+1])

            if signal and signal.direction == 'long' and position == 0:
                position = self._execute_buy(signal, i)
            elif signal and signal.direction == 'short' and position > 0:
                capital = self._execute_sell(signal, i, position)
                position = 0

            portfolio_value = capital + position * self.data.iloc[i]['close']
            results.append({
                'timestamp': self.data.index[i],
                'portfolio_value': portfolio_value,
                'position': position,
                'capital': capital,
            })

        return pd.DataFrame(results).set_index('timestamp')
```

### 6.2 Performance-Metriken

**Sharpe Ratio:**
```
Sharpe = (R_p - R_f) / σ_p

wobei:
  R_p = Portfoliorendite
  R_f = Risikofreier Zins
  σ_p = Standardabweichung der Renditen
```

**Sortino Ratio (Downside-Risiko):**
```
Sortino = (R_p - R_f) / σ_downside

σ_downside = √(1/N × Σ(min(r_i, 0))²)
```

**Maximaler Drawdown:**
```
MDD = max((Peak - Trough) / Peak)

über den gesamten Backtest-Zeitraum
```

**Calmar Ratio:**
```
Calmar = Annualized_Return / Max_Drawdown
```

**Profit Factor:**
```
Profit Factor = Σ(Gross_Profits) / Σ(Gross_Losses)

> 1.5 = gut, > 2.0 = exzellent
```

**Weitere wichtige Metriken:**
```python
def compute_metrics(equity_curve, trades):
    returns = equity_curve.pct_change().dropna()

    # Sharpe (annualisiert, 252 Tage)
    sharpe = returns.mean() / returns.std() * np.sqrt(252)

    # Sortino
    downside = returns[returns < 0]
    sortino = returns.mean() / downside.std() * np.sqrt(252)

    # Max Drawdown
    cumulative = (1 + returns).cumprod()
    peak = cumulative.expanding().max()
    drawdown = (cumulative - peak) / peak
    max_dd = drawdown.min()

    # Win Rate
    winning = trades[trades['pnl'] > 0]
    win_rate = len(winning) / len(trades)

    # Avg Win / Avg Loss
    avg_win = winning['pnl'].mean() if len(winning) > 0 else 0
    avg_loss = abs(trades[trades['pnl'] < 0]['pnl'].mean())

    # Profit Factor
    profit_factor = winning['pnl'].sum() / abs(trades[trades['pnl'] < 0]['pnl'].sum())

    # Expectancy
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    return {
        'sharpe': sharpe,
        'sortino': sortino,
        'max_drawdown': max_dd,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'expectancy': expectancy,
        'total_trades': len(trades),
        'total_return': (equity_curve.iloc[-1] / equity_curve.iloc[0]) - 1,
    }
```

### 6.3 Walk-Forward-Optimierung

**Warum Walk-Forward essential ist:**
- Verhindert Overfitting auf historische Daten
- Simuliert realen Einsatz: Trainiere auf Vergangenheit, teste auf Zukunft
- **Goldstandard** für Strategievalidierung

```
Zeitachse:
|──── Training ────|── Test ──|
                    |──── Training ────|── Test ──|
                                        |── Training ──|── Test ──|

Window 1: Train [0:500]    → Test [500:600]
Window 2: Train [100:600]  → Test [600:700]
Window 3: Train [200:700]  → Test [700:800]
...
```

```python
def walk_forward_optimization(data, strategy_class, param_grid,
                              train_window=500, test_window=100, step=100):
    results = []

    for start in range(0, len(data) - train_window - test_window, step):
        train_data = data.iloc[start:start+train_window]
        test_data = data.iloc[start+train_window:start+train_window+test_window]

        # Grid Search auf Training
        best_params = None
        best_score = -np.inf
        for params in param_grid:
            strategy = strategy_class(**params)
            score = backtest(train_data, strategy)['sharpe']
            if score > best_score:
                best_score = score
                best_params = params

        # Beste Parameter auf Test-Set evaluieren
        strategy = strategy_class(**best_params)
        test_result = backtest(test_data, strategy)
        results.append(test_result)

    return aggregate_results(results)
```

### 6.4 Backtesting-Fallen (Beware!)

| Falle | Beschreibung | Lösung |
|---|---|---|
| Look-Ahead Bias | Zukunftsdaten im Training | Striktes Train/Test-Split |
| Survivorship Bias | Nur noch existierende Assets | Delisted-Coins einbeziehen |
| Overfitting | Zu viele Parameter | Walk-Forward + Simplizität |
| Slippage Ignorieren | Ideale Ausführung angenommen | Realistische Slippage-Modelle |
| Transaction Costs | Kommissionen vergessen | Maker/Taker-Fees einrechnen |
| Market Impact | Große Orders bewegen den Markt | Volume-basierte Limits |
| Curve Fitting | Parameter auf Historie optimiert | Out-of-Sample-Validierung |
| Data Snooping | Mehrfaches Testen auf selben Daten | Bonferroni-Korrektur |

---

## 7. Risikomanagement & Robustheit

### 7.1 Risikomanagement-Framework

```
┌────────────────────────────────────────────────────┐
│            RISIKOMANAGEMENT-HIERARCHIE              │
│                                                    │
│  Ebene 1: Position-Level                          │
│  ├─ Max. Risk pro Trade: 1-2% des Kapitals        │
│  ├─ Stop-Loss zwingend                            │
│  └─ Positionsgröße via Kelly/Risk-Parity          │
│                                                    │
│  Ebene 2: Portfolio-Level                         │
│  ├─ Max. Drawdown-Limit: 15-20%                   │
│  ├─ Max. Korrelations-Exposure                    │
│  ├─ Sektorspezifische Caps                        │
│  └─ Gesamtexposure-Limit                          │
│                                                    │
│  Ebene 3: System-Level                            │
│  ├─ Circuit Breaker bei Extrem-Volatilität        │
│  ├─ Daily Loss-Limit (z.B. 5%)                    │
│  ├─ Model-Performance-Monitoring                  │
│  └─ Automatischer Trading-Stopp bei Anomalien     │
└────────────────────────────────────────────────────┘
```

### 7.2 Drawdown-Analyse

```python
def drawdown_analysis(equity_curve):
    """Umfassende Drawdown-Analyse"""
    returns = equity_curve.pct_change().dropna()
    cumulative = (1 + returns).cumprod()
    peak = cumulative.expanding().max()
    drawdown = (cumulative - peak) / peak

    # Drawdown-Perioden identifizieren
    in_drawdown = drawdown < 0
    dd_starts = in_drawdown & ~in_drawdown.shift(1).fillna(False)
    dd_ends = ~in_drawdown & in_drawdown.shift(1).fillna(False)

    dd_periods = []
    for start_idx in dd_starts[dd_starts].index:
        end_candidates = dd_ends[dd_ends.index > start_idx]
        end_idx = end_candidates.index[0] if len(end_candidates) > 0 else drawdown.index[-1]
        dd_periods.append({
            'start': start_idx,
            'end': end_idx,
            'duration_days': (end_idx - start_idx).days,
            'max_drawdown': drawdown[start_idx:end_idx].min(),
            'recovery_days': (end_idx - drawdown[start_idx:end_idx].idxmin()).days,
        })

    return {
        'max_drawdown': drawdown.min(),
        'avg_drawdown': np.mean([p['max_drawdown'] for p in dd_periods]),
        'max_duration': max(p['duration_days'] for p in dd_periods),
        'avg_duration': np.mean([p['duration_days'] for p in dd_periods]),
        'dd_frequency': len(dd_periods),
        'recovery_factor': abs(cumulative.iloc[-1] / drawdown.min()),
    }
```

### 7.3 Modell-Robustheit

**Cross-Validation für Zeitreihen:**
```python
from sklearn.model_selection import TimeSeriesSplit

tscv = TimeSeriesSplit(n_splits=5)
for train_idx, test_idx in tscv.split(features):
    # Niemals zufälliges Split bei Zeitreihen!
    X_train, X_test = features.iloc[train_idx], features.iloc[test_idx]
    y_train, y_test = target.iloc[train_idx], target.iloc[test_idx]
```

**Stresstest-Szenarien:**
```python
stress_scenarios = {
    'flash_crash':     {'price_drop': -20, 'volatility_mult': 5},
    'black_swan':      {'price_drop': -40, 'volatility_mult': 10},
    'liquidity_crisis': {'volume_drop': -80, 'spread_mult': 5},
    'correlation_break': {'corr_shift': +0.5},
    'regime_change':   {'trend_reversal': True},
}

for name, scenario in stress_scenarios.items():
    stressed_data = apply_stress(historical_data, scenario)
    result = backtest(stressed_data, strategy)
    print(f"{name}: Max DD = {result['max_drawdown']:.2%}")
```

---

## 8. Datenquellen, Feature-Engineering & Vorverarbeitung

### 8.1 Datenquellen

**Krypto-Daten:**

| Quelle | Daten | Kosten | Latenz |
|---|---|---|---|
| **Binance API** | OHLCV, Orderbuch, Trades | Kostenlos | ~10ms |
| **Bitget API** | OHLCV, Funding, OI | Kostenlos | ~20ms |
| **CoinGecko** | Preise, Market Cap | Freemium | ~1min |
| **CryptoCompare** | Historisch, News | Freemium | ~30s |
| **Glassnode** | On-Chain | Ab $39/Mo | ~15min |
| **CryptoQuant** | On-Chain, Exchange | Ab $29/Mo | ~5min |
| **Coinglass** | Liquidations, Funding | Freemium | ~1min |

**Gold- & Makro-Daten:**

| Quelle | Daten | Kosten |
|---|---|---|
| **FRED (St. Louis Fed)** | Zinsen, CPI, GDP, Arbeitsmarkt | Kostenlos |
| **Yahoo Finance** | GLD, GC=F Preise | Kostenlos |
| **World Gold Council** | Gold Demand, Reserven | Kostenlos |
| **Bloomberg** | Vollständige Makro-Daten | Ab $2k/Mo |
| **TradingEconomics** | Makro-Kalender | Freemium |

### 8.2 Feature-Engineering

**Feature-Kategorien (80+ Features):**

```
┌─────────────────────────────────────────────────────┐
│              FEATURE ENGINEERING                     │
├─────────────┬──────────────┬────────────────────────┤
│ Preis-basiert│ Volumen      │ Volatilität            │
│ ├─ Returns   │ ├─ OBV       │ ├─ Realized Vol        │
│ ├─ Log-Ret   │ ├─ VWAP      │ ├─ Parkinson Vol       │
│ ├─ Momentum  │ ├─ Vol SMA   │ ├─ Garman-Klass        │
│ ├─ ROC       │ ├─ A/D Line  │ ├─ ATR                 │
│ └─ Cum. Ret  │ └─ CMF       │ ├─ Bollinger Width     │
│              │              │ └─ Keltner Width        │
├─────────────┼──────────────┼────────────────────────┤
│ Trend        │ Oszillatoren │ Sentiment/On-Chain      │
│ ├─ SMA/EMA   │ ├─ RSI       │ ├─ Fear & Greed        │
│ ├─ MACD      │ ├─ Stochastic│ ├─ Social Volume       │
│ ├─ ADX       │ ├─ CCI       │ ├─ Funding Rate        │
│ ├─ Ichimoku  │ ├─ Williams% │ ├─ Exchange Flow       │
│ └─ Parabolic │ └─ MFI       │ ├─ Active Addresses    │
│   SAR        │              │ └─ Whale Transactions   │
├─────────────┼──────────────┼────────────────────────┤
│ Statistisch  │ Zeit-basiert │ Makroökonomisch         │
│ ├─ Autokorr  │ ├─ Hour S/C  │ ├─ DXY                  │
│ ├─ Partial   │ ├─ Day of Wk │ ├─ US 10Y Yield        │
│ ├─ Hurst Exp │ ├─ Is Weekend│ ├─ Real Yield          │
│ ├─ Entropy   │ └─ Session   │ ├─ CPI/YoY             │
│ └─ Kurtosis  │              │ └─ VIX                  │
└─────────────┴──────────────┴────────────────────────┘
```

### 8.3 Datenvorverarbeitung

**Pipeline:**
```python
class DataPreprocessor:
    """Vollständige Vorverarbeitung-Pipeline"""

    def clean(self, df):
        """1. Bereinigung"""
        df = df.drop_duplicates()
        df = df[~df.index.duplicated(keep='first')]
        df = df.sort_index()
        # Fehlende Kerzen forward-fillen (24/7 Markt!)
        df = df.asfreq('1H', method='ffill')
        return df

    def handle_outliers(self, df, method='iqr'):
        """2. Ausreißer-Behandlung"""
        for col in df.select_dtypes(include=[np.number]).columns:
            if method == 'iqr':
                Q1, Q3 = df[col].quantile(0.25), df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower, upper = Q1 - 3*IQR, Q3 + 3*IQR
                df[col] = df[col].clip(lower, upper)
        return df

    def normalize(self, df, method='robust'):
        """3. Normalisierung"""
        if method == 'robust':
            scaler = RobustScaler()  # Robust gegen Ausreißer
        elif method == 'minmax':
            scaler = MinMaxScaler()
        df_scaled = pd.DataFrame(
            scaler.fit_transform(df),
            columns=df.columns, index=df.index
        )
        return df_scaled, scaler

    def create_sequences(self, data, seq_len, horizon):
        """4. Sequenzen für DL-Modelle"""
        X, y = [], []
        for i in range(len(data) - seq_len - horizon + 1):
            X.append(data[i:i+seq_len])
            y.append(data[i+seq_len:i+seq_len+horizon, 0])  # Close-Preis
        return np.array(X), np.array(y)
```

---

## 9. Echtzeit-Implementierung & Deployment

### 9.1 Systemarchitektur

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUKTIONS-ARCHITEKTUR                       │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  Data Layer   │  │ Compute Layer│  │  Action Layer        │ │
│  │              │  │              │  │                      │ │
│  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────────────┐ │ │
│  │ │ WebSocket│ │  │ │ Feature  │ │  │ │ Signal Validator │ │ │
│  │ │ Feeds    │ │  │ │ Engine   │ │  │ │                  │ │ │
│  │ │ (Binance,│ │  │ │ (pandas- │ │  │ │ Risk Checks      │ │ │
│  │ │  Bitget) │ │  │ │  ta,     │ │  │ │                  │ │ │
│  │ │          │ │  │ │  custom) │ │  │ │ Position Sizing  │ │ │
│  │ │  Bitget) │ │  │ │  custom) │ │  │ │ Position Sizing  │ │ │
│  │ └────┬─────┘ │  │ └────┬─────┘ │  │ └────────┬─────────┘ │ │
│  │      │       │  │      │       │  │          │           │ │
│  │ ┌────▼─────┐ │  │ ┌────▼─────┐ │  │ ┌────────▼─────────┐ │ │
│  │ │ Redis    │ │  │ │ Model    │ │  │ │ Order Execution  │ │ │
│  │ │ Cache    │ │  │ │ Ensemble │ │  │ │ (Exchange API)   │ │ │
│  │ │ (Latest  │ │  │ │ (ONNX/   │ │  │ │                  │ │ │
│  │ │  State)  │ │  │ │  Torch)  │ │  │ │ Slippage Control │ │ │
│  │ └──────────┘ │  │ └──────────┘ │  │ └──────────────────┘ │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Monitoring & Observability                   │  │
│  │  Prometheus → Grafana │ AlertManager │ PagerDuty         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Latenz-Optimierung

**Kritischer Pfad: Tick → Signal → Order**
```
WebSocket Tick     Feature Calc    Model Inference    Order Submit
─────────────────────────────────────────────────────────────────
   < 5ms            < 10ms          < 50ms             < 20ms
                                           ↓
                              Gesamt-Latenz Target: < 100ms
```

**Inferenz-Latenz pro Modelltyp (CPU, Single Sample, gemessen):**

| Modell | Typische Latenz | ONNX-Optimiert | Für Echtzeit? | Hinweis |
|---|---|---|---|---|
| GARCH(1,1) | 2-8ms | — | Ja | statsmodels, synchron → `run_in_executor` |
| XGBoost (100 Trees) | 1-5ms | — | Ja | Nativ schnell, kein ONNX nötig |
| LightGBM (100 Trees) | 1-3ms | — | Ja | Schnellstes GBM |
| LSTM (3 Layer, CPU) | 50-200ms | 10-30ms | Grenzwertig | **PyTorch blockiert async Loop** |
| TFT (full model) | 100-500ms | 20-80ms | Nein (ohne ONNX) | Nur mit ONNX-Server einsetzbar |
| Transformer (small) | 80-300ms | 15-50ms | Grenzwertig | ONNX-Export zwingend |
| RL (PPO Inference) | 5-20ms | — | Ja | Nur Forward-Pass, trainiert offline |
| ARIMA (fitted) | 5-15ms | — | Ja | Einmal fitted, predict ist schnell |
| Scoring (bestehend) | < 1ms | — | Ja | Reine Arithmetik, kein ML |

> **Konsequenz für Architektur:** XGBoost/LightGBM + GARCH direkt im Bot-Prozess.
> LSTM/TFT/Transformer **zwingend** via separatem ONNX-Server oder `loop.run_in_executor(None, model.predict, features)` — niemals synchron im Event Loop.

**Optimierungsstrategien:**

1. **Model Serving:**
   - ONNX Runtime statt PyTorch (5-10x schneller)
   - Batch-Prediction bei niedriger Frequenz
   - Model-Warming beim Startup

2. **Daten-Caching:**
   - Redis für neueste Marktdaten
   - Pre-computed Features für häufige Abfragen
   - Incremental Updates statt Neuberechnung

3. **Async-IO:**
```python
import asyncio
import websockets

async def market_data_stream(symbols):
    """Parallele WebSocket-Verbindungen"""
    tasks = [stream_symbol(s) for s in symbols]
    async for update in asyncio.gather(*tasks):
        await process_update(update)

async def process_update(update):
    """Non-blocking Processing Pipeline"""
    features = await compute_features(update)  # async calc
    prediction = await model.predict(features)  # async inference
    if signal := generate_signal(prediction):
        await execute_order(signal)  # async execution
```

### 9.3 Deployment-Strategien

**Docker Compose (bestehend im ai4trade-bot):**
```yaml
services:
  trading-engine:
    build: .
    environment:
      - EXCHANGE_PROVIDER=bitget
      - MODEL_BACKEND=onnx
    depends_on:
      - redis
      - model-server
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'

  model-server:
    image: mcr.microsoft.com/azureml/onnxruntime-server
    volumes:
      - ./models:/models
    ports:
      - "8888:8888"

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb

  prometheus:
    image: prom/prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
```

**Blue-Green Deployment für Modell-Updates:**
```
┌───────────────┐     ┌───────────────┐
│  Blue (v1.0)  │     │ Green (v1.1)  │
│  LIVE Traffic │     │  Shadow Mode  │
│               │     │  (Paper Trade)│
└───────┬───────┘     └───────┬───────┘
        │                     │
        └───── Switch ────────┘
        (wenn Green > Blue im Paper Test)
```

### 9.4 Monitoring & Alerting

**Kritische Metriken:**
```python
monitoring_metrics = {
    'latency': {
        'tick_to_signal_p50': 'target < 50ms',
        'tick_to_signal_p99': 'target < 200ms',
        'order_execution_p50': 'target < 30ms',
    },
    'model': {
        'prediction_accuracy_1h': 'min 52%',
        'signal_confidence_avg': 'min 0.6',
        'model_drift_score': 'max 0.1',
    },
    'trading': {
        'daily_pnl': 'alert if < -2%',
        'drawdown_current': 'alert if > 10%',
        'win_rate_7d': 'alert if < 40%',
        'sharpe_rolling_30d': 'alert if < 0.5',
    },
    'system': {
        'api_error_rate': 'max 1%',
        'websocket_reconnects': 'max 5/hour',
        'memory_usage': 'max 80%',
        'cpu_usage': 'max 70%',
    },
}
```

---

## 10. Bewertungsmatrix & Empfehlungen

### 10.1 Modell-Bewertung nach Kriterium

| Modell | Prognosegüte | Interpretierbarkeit | Trainingszeit | Echtzeit-Fähigkeit | Overfitting-Risiko | Gesamtbewertung |
|---|---|---|---|---|---|---|
| ARIMA | ★★☆☆☆ | ★★★★★ | ★★★★★ | ★★★★★ | ★★☆☆☆ | Mittel |
| GARCH | ★★★★☆ (Vol.) | ★★★★☆ | ★★★★★ | ★★★★★ | ★★☆☆☆ | Hoch (für Vol.) |
| ETS | ★★☆☆☆ | ★★★★★ | ★★★★★ | ★★★★★ | ★☆☆☆☆ | Niedrig |
| State Space | ★★★☆☆ | ★★★★☆ | ★★★★☆ | ★★★★★ | ★★☆☆☆ | Mittel-Hoch |
| XGBoost | ★★★★☆ | ★★★☆☆ | ★★★★☆ | ★★★★☆ | ★★★☆☆ | Hoch |
| LightGBM | ★★★★☆ | ★★★☆☆ | ★★★★★ | ★★★★☆ | ★★★☆☆ | Hoch |
| LSTM | ★★★☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★☆ | Mittel |
| TFT | ★★★★★ | ★★★★☆ | ★★☆☆☆ | ★★★☆☆ | ★★★☆☆ | Sehr Hoch |
| Transformer | ★★★★☆ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★★★☆ | Hoch |
| RL (PPO) | ★★★★☆ (Aktion) | ★★☆☆☆ | ★☆☆☆☆ | ★★★☆☆ | ★★★★☆ | Hoch |
| Ensemble | ★★★★★ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★☆☆☆ | Sehr Hoch |

### 10.2 Empfohlener Technologie-Stack für ai4trade-bot

> **Architektur-Entscheidung — XGBoost zuerst, kein GRU/LSTM im Event Loop:**
> Der ai4trade-bot läuft auf einem **asyncio Event Loop** (WebSocket-Feeds, Signal-Loop).
> Sync-PyTorch blockiert diesen Loop — GRU/LSTM sind daher für den kritischen Pfad
> ausgeschlossen. XGBoost/LightGBM sind nativ schnell (1-5ms) und async-kompatibel.
> DL-Modelle nur via ONNX-Export + separatem Server oder `run_in_executor`.

**Priorität 1 — Fundament (sofort umsetzbar):**
1. **GARCH(1,1)** — Volatilitätsmodellierung für Stop-Loss und Sizing
2. **XGBoost/LightGBM** — Primäres Vorhersagemodell (async-sicher, 1-5ms Latenz)
3. **pandas-ta** — Feature-Generierung (bestehend erweitern, pure Python)

**Priorität 2 — Erweiterung (mittelfristig, 3-6 Monate):**
4. **Temporal Fusion Transformer** — Multivariate Prognose mit Unsicherheit (NUR via ONNX-Server)
5. **Sentiment-Pipeline** — FinBERT/LLM-basierte Stimmungsanalyse (bestehend erweitern)
6. **Walk-Forward Backtesting** — Robuste Strategievalidierung

**Priorität 3 — Fortgeschritten (langfristig, >12 Monate):**
7. **Reinforcement Learning (PPO)** — Adaptive Portfolio-Optimierung (VORBEDINGUNG: 2+ Jahre Daten, stabiles Basismodell, Backtesting-Infrastruktur)
8. **Zustandsraummodelle** — Online-adaptive Prognose
9. **Regime-Switching (HMM)** — Marktphasen-Erkennung

### 10.3 Integration in bestehenden ai4trade-bot

```
BESTEHEND:                    ERWEITERT:
─────────────────────         ┌─────────────────────────────┐
                              │  Data Layer                  │
  Bitget API ───────────────→ │  ├─ Bitget (bestehend)      │
                              │  ├─ Binance (zusätzlich)     │
                              │  ├─ FRED (Makro/Gold)        │
                              │  └─ Glassnode (On-Chain)     │
                              ├─────────────────────────────┤
  core/technical.py ────────→ │  Feature Engine              │
  (RSI, MACD, EMA, BB)        │  ├─ pandas-ta (bestehend+50)│
                              │  ├─ GARCH Volatility         │
                              │  ├─ On-Chain Features        │
                              │  └─ Macro Features           │
                              ├─────────────────────────────┤
  core/strategy.py ─────────→ │  Model Ensemble              │
  (Scoring-basiert)           │  ├─ XGBoost (neu, primär)   │
                              │  ├─ GARCH (neu, Volatilität) │
                              │  ├─ TFT (neu, multivariat)   │
                              │  └─ Scoring (bestehend, als  │
                              │     Fallback/Feature)        │
                              ├─────────────────────────────┤
  ai/sentiment.py ──────────→ │  Signal Router (bestehend,   │
  (LLM-basiert)               │  erweitert um Ensemble)      │
                              ├─────────────────────────────┤
  Fehlt komplett ───────────→ │  Backtesting Engine          │
                              │  ├─ Walk-Forward Framework   │
                              │  ├─ Performance Metrics      │
                              │  └─ Stress Testing           │
                              ├─────────────────────────────┤
  Docker (bestehend) ───────→ │  Deployment (bestehend +     │
  Prometheus/Grafana          │  Model-Serving Erweiterung)  │
                              └─────────────────────────────┘
```

---

## 11. Architektur-Blueprint für ai4trade-bot

### 11.1 Dateistruktur (vorgeschlagen)

```
ai4trade-bot/
├── core/
│   ├── technical.py          # Bestehend: RSI, MACD, etc.
│   ├── strategy.py           # Bestehend: Scoring-Strategie
│   ├── market_signals.py     # Bestehend: Market Context
│   ├── models/               # NEU: Vorhersagemodelle
│   │   ├── __init__.py
│   │   ├── garch.py          # GARCH Volatilitätsmodell
│   │   ├── xgboost_model.py  # XGBoost Vorhersage
│   │   ├── lstm_model.py     # LSTM Deep Learning
│   │   ├── tft_model.py      # Temporal Fusion Transformer
│   │   ├── ensemble.py       # Ensemble-Koordination
│   │   └── regime.py         # HMM Regime-Detektion
│   ├── features/             # NEU: Feature-Engineering
│   │   ├── __init__.py
│   │   ├── technical.py      # Erweiterte TA-Features
│   │   ├── volatility.py     # Volatilitäts-Features
│   │   ├── onchain.py        # On-Chain-Features
│   │   ├── macro.py          # Makro-Features (Gold)
│   │   └── time_features.py  # Zeitbasierte Features
│   └── signals/              # NEU: Signal-Generierung
│       ├── __init__.py
│       ├── generator.py      # Entry/Exit-Signale
│       ├── risk.py           # Risikomanagement
│       ├── sizing.py         # Positionsgrößen
│       └── validator.py      # Signal-Validierung
├── backtest/                 # NEU: Backtesting
│   ├── __init__.py
│   ├── engine.py             # Vectorized Backtest
│   ├── metrics.py            # Performance-Metriken
│   ├── walk_forward.py       # Walk-Forward Optimierung
│   └── stress_test.py        # Stresstest-Szenarien
├── data/                     # NEU: Datenmanagement
│   ├── __init__.py
│   ├── sources/              # Datenquellen-Adapter
│   │   ├── binance.py
│   │   ├── fred.py
│   │   └── glassnode.py
│   ├── preprocessor.py       # Datenvorverarbeitung
│   └── store.py              # Lokaler Daten-Cache
├── models/                   # Trainierte Modelle (Artifacts)
│   ├── xgboost_v1.json
│   ├── lstm_v1.pt
│   └── garch_params.pkl
└── config/
    └── model_config.yml      # NEU: Modell-Konfiguration
```

### 11.2 Empfohlene Python-Abhängigkeiten

```toml
# pyproject.toml (Auszug)
# Aufgeteilt in Core (lean, immer installiert) und Optional-Gruppen

[project]
dependencies = [
    # Bestehend
    "ccxt>=4.0",
    "pandas>=2.0",
    "numpy>=1.24",

    # NEU — Statistische Modelle (leichtgewichtig)
    "arch>=6.0",              # GARCH (~5MB)
    "statsmodels>=0.14",      # ARIMA, State Space (~15MB)
    "pmdarima>=2.0",          # Auto-ARIMA (~8MB)

    # NEU — Machine Learning (produktiv benötigt)
    "xgboost>=2.0",           # Primäres Modell (~30MB)
    "lightgbm>=4.0",          # Alternative GBM (~15MB)
    "scikit-learn>=1.3",      # Preprocessing, Metrics (~25MB)

    # NEU — Technical Analysis (Pure Python, kein System-Build nötig)
    "pandas-ta>=0.3",         # Primary TA-Lib Ersatz — pure Python
    # ta-lib NICHT als Core-Dependency — C-Library braucht System-Build

    # NEU — ONNX Runtime für Production Inference (leichtgewichtig)
    "onnxruntime>=1.16",      # ~30MB, CPU-only, kein PyTorch nötig
]

[project.optional-dependencies]
# Gruppe: Deep Learning (nur für Training, nicht für Produktion)
# PyTorch ist ~2GB+ und blockiert async — nur auf Trainings-Maschinen
dl-training = [
    "torch>=2.1",             # ~2GB — NUR für Training/ONNX-Export
    "pytorch-forecasting>=1.0",  # TFT Training
]

# Gruppe: Reinforcement Learning (langfristig, >12 Monate)
rl = [
    "gymnasium>=0.29",
    "stable-baselines3>=2.2",
    "shimmy>=1.0",            # Gymnasium-Kompatibilität
]

# Gruppe: Backtesting & Analyse (Entwicklungs-Tools)
backtest = [
    "vectorbt>=0.26",         # WARN: numba-Dependency, Windows-problematisch
    "empyrical>=1.0",         # Performance-Metriken
    "matplotlib>=3.7",        # Visualisierung
]

# Gruppe: TA-Lib (optional, wenn C-Build verfügbar)
talib = [
    "ta-lib>=0.4.28",         # BRAUCHT: System-Build (apt/brew install ta-lib)
]

# Alle optionalen Gruppen auf einmal
all = ["ai4trade-bot[dl-training,rl,backtest,talib]"]
```

> **Install-Hinweis:** `pip install -e ".[backtest]"` für Entwicklung mit Backtesting.
> Produktiv-Docker: Nur Core-Dependencies. Modelle werden als ONNX-Dateien geliefert.
> TA-Lib C-Build auf Windows: `conda install -c conda-forge ta-lib` oder vcpkg.

---

## 12. Quellen & Referenzen

### Statistische Grundlagen
- IBKR Quant: Advanced Time Series Analysis in Finance
- Robot Wealth: ARIMA/GARCH for FX — Are Predictions Profitable?
- QuantInsti: Forecasting Stock Prices Using ARIMA Model
- Diva-Portal: ARIMA and GARCH Models in Portfolio Management

### Deep Learning & Transformer
- arXiv 2403.03606: Enhancing Price Prediction with Transformers
- IEEE 10393319: Cryptocurrency Price Prediction with LSTM and Transformer
- ScienceDirect: Review of Deep Learning Models for Crypto Price Prediction
- MDPI Symmetry: From LSTM to GPT-2 for Cryptocurrency Forecasting

### Reinforcement Learning
- arXiv 2304.06037: Quantitative Trading using Deep Q Learning
- Cureus: Deep RL for Stock, Portfolio, and Crypto Trading (2020-2025)
- FinRL-Library (GitHub/firmai): End-to-End DRL for Automated Trading

### Gold & Makroökonomie
- MDPI Risks: Safe-Haven Assets, Financial Crises, and Macro Variables
- MDPI Finance: Framework for Gold Price Prediction (Classical + ML)
- LSEG: Gold's Meteoric Rise in 2025 — Safe Haven amid Global Uncertainty
- SSRN: Iterated Dynamic Model Averaging for Gold Price Forecasting

### Backtesting & Risk Management
- LuxAlgo: Time Series Analysis in Algo Trading
- AvaTrade: Backtesting Trading Strategies Complete Guide
- Bitsgap: Crypto Backtesting Guide 2025

### Feature Engineering & Microstruktur
- arXiv 2306.08157: Causal Feature Engineering for Crypto
- MDPI: Multi-Timeframe Feature Engineering for Bitcoin
- Springer: Crypto Volatility Forecasting — HAR, Sentiment, ML
- Cornell: Market Microstructure Metrics for Crypto Price Dynamics

### Echtzeit-Infrastruktur
- AWS: Optimize Tick-to-Trade Latency for Digital Assets
- Medium: Low-Latency HFT System for Cryptocurrency Markets
- BSO: Achieving Ultra-Low Latency in Trading Infrastructure

---

*Dieses Dokument dient als Forschungsgrundlage und Entscheidungshilfe für die Weiterentwicklung des ai4trade-bot Trading-Systems.*
