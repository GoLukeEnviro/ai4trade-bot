# Contributing zu Rainbow

Rainbow ist ein Open-Source-Projekt. Wir freuen uns ueber Pull Requests, Bug Reports und neue Collectors.

## Wie man einen neuen Collector schreibt

### Schritt 1: Von BaseCollector erben

Jeder Collector erbt von `BaseCollector` und implementiert `collect()`:

```python
from rainbow.collectors.base import BaseCollector
from rainbow.models.signal import CryptoSignal, SignalType, Direction

class MyCollector(BaseCollector):
    def __init__(self, api_key: str, assets: list[str]):
        self._api_key = api_key
        self._assets = assets

    @property
    def name(self) -> str:
        return "my_collector"  # Eindeutiger Name

    async def collect(self) -> list[CryptoSignal]:
        """MUSS list[CryptoSignal] zurueckgeben."""
        signals = []
        for asset in self._assets:
            # Daten abrufen
            data = await self._fetch_data(asset)
            # In CryptoSignal umwandeln
            signal = CryptoSignal(
                source=self.name,
                asset=asset,
                signal_type=SignalType.SOCIAL,
                direction=Direction.BULLISH,
                strength=0.8,
                confidence=0.7,
                metadata={"raw": data}
            )
            signals.append(signal)
        return signals
```

### Schritt 2: Fehlerbehandlung

Bei Fehlern `CollectorError` werfen (inkl. Collector-Name):

```python
from rainbow.exceptions import CollectorError

async def collect(self) -> list[CryptoSignal]:
    try:
        data = await self._fetch_data()
    except Exception as exc:
        raise CollectorError(self.name, f"Datenabruf fehlgeschlagen: {exc}") from exc
```

### Schritt 3: Tests schreiben

Tests sind Pflicht. Mindestens ein Unit-Test pro Collector:

```python
# rainbow/tests/test_my_collector.py
import pytest
from rainbow.collectors.my_collector import MyCollector
from rainbow.models.signal import SignalType

@pytest.mark.asyncio
async def test_my_collector_returns_signals():
    collector = MyCollector(api_key="test", assets=["BTC"])
    signals = await collector.collect()

    assert len(signals) > 0
    assert all(s.source == "my_collector" for s in signals)
    assert all(s.asset == "BTC" for s in signals)
```

### Schritt 4: Collector registrieren

In `rainbow/main.py`:

```python
from rainbow.collectors.my_collector import MyCollector

my_collector = MyCollector(
    api_key=settings.my_api_key,
    assets=["BTC", "ETH"]
)
engine.register_collector(my_collector)
```

### Schritt 5: Konfiguration

In `rainbow/config/rainbow.example.yml`:

```yaml
collectors:
  my_collector:
    enabled: false
    interval_seconds: 300
    params:
      assets: [BTC, ETH]
```

## Coding-Konventionen

### Linting und Formatting

Wir nutzen Ruff. Vor jedem Commit ausfuehren:

```bash
ruff check rainbow/          # Linting
ruff format rainbow/         # Formatting
```

Bei CI-Fehlern: Ruff-Ausgabe lesen, Fehler fixen, neu committen.

### Type-Hints

Pflicht. Alle oeffentlichen Funktionen muessen typisiert sein:

```python
async def fetch_data(asset: str) -> dict[str, Any]:
    pass
```

### Async-First

Alle I/O-Operationen muessen asynchron sein (`async def`, `await`). Keine blocking calls in async Functions.

### Pydantic-Modelle

CryptoSignal ist non-negotiable. Collectors muessen exakt dieses Modell produzieren:

```python
signal = CryptoSignal(
    source="mein_collector",
    asset="BTC",
    signal_type=SignalType.TECHNICAL,
    direction=Direction.BULLISH,
    strength=0.8,
    confidence=0.7,
    metadata={...}  # Collectorspezifische Daten
)
```

Keine zusaetzlichen Felder in CryptoSignal. Collectorspezifische Daten in `metadata` oder `raw_data`.

### Docstrings

Oeffentliche Funktionen brauchen kurze Docstrings:

```python
async def collect(self) -> list[CryptoSignal]:
    """Sammle Daten von API und gib CryptoSignal-Liste zurueck."""
```

## Test-Anforderungen

### Test-Struktur

Tests liegen in `rainbow/tests/`. Naming: `test_<modul>.py`.

### Mindest-Anforderung

1. **Unit-Tests**: Fuer Business-Logik (z.B. Scoring, Signal-Transformation)
2. **Collector-Tests**: Mindestens ein Test pro Collector (Mocked Data)
3. **Integration-Tests**: Fuer API-Endpoints (optional)

### Pytest-Marker

Verwende Marker fuer Test-Kategorisierung:

```python
import pytest

@pytest.mark.asyncio
async def test_something():
    pass

@pytest.mark.unit
def test_pure_function():
    pass

@pytest.mark.integration
async def test_api_endpoint():
    pass
```

### Tests ausfuehren

```bash
# Alle Tests
pytest rainbow/tests/

# Nur Unit-Tests
pytest rainbow/tests/ -m unit

# Mit Coverage
pytest rainbow/tests/ --cov=rainbow --cov-report=term-missing
```

### Test-Daten

Keine externen API-Calls in Tests. Mocking verwenden:

```python
@pytest.mark.asyncio
async def test_collector_with_mocked_api(mocker):
    mock_response = {"price": 50000, "trend": "up"}
    mocker.patch("my_collector.fetch_api", return_value=mock_response)

    collector = MyCollector(api_key="test")
    signals = await collector.collect()

    assert len(signals) > 0
```

## Commit-Style

Wir nutzen Conventional Commits auf Deutsch. Commit-Message = Why, nicht What.

### Format

```
<type>: <kurzbeschreibung>
```

### Types

- `feat`: Neues Feature
- `fix`: Bugfix
- `refactor`: Refactoring (keine Funktionsaenderung)
- `test`: Tests hinzugefuegt/geaendert
- `docs`: Dokumentation
- `chore`: Dependencies, Config, etc.
- `perf`: Performance-Verbesserung

### Beispiele

```
feat: telegram collector hinzu
fix: null-pointer in scorer bei leeren signal-listen
refactor: async loop in webhooks ueberarbeitet
test: integration test fuer /signals/latest
docs: api doku erweitert
```

## PR-Prozess

### 1. Branch erstellen

```bash
git checkout -b feat/telegram-collector
```

### 2. Aenderungen committen

```bash
git add rainbow/collectors/telegram_collector.py
git commit -m "feat: telegram collector hinzu"
```

### 3. Tests ausfuehren

```bash
pytest rainbow/tests/
ruff check rainbow/
```

### 4. Push und PR

```bash
git push origin feat/telegram-collector
```

PR erstellen mit:
- **Titel**: Kurz (<70 Zeichen), z.B. "feat: Telegram Collector"
- **Summary**: 1-3 Bulletpoints, was geaendert wurde
- **Testing**: Welche Tests wurden ausgefuehrt

### 5. Review

CI muss gruen sein. Ein Reviewer wird Feedback geben. Nach Review: Aenderungen committen, CI checken, Reviewer bestaetigen.

### 6. Merge

Squash-Merge nach main. Branch kann lokal geloescht werden.

## Code-Review

### Was wir pruefen

1. **Funktion**: Erfuellt die Aenderung den Zweck?
2. **Tests**: Gibt es Tests? Laufen sie durch?
3. **Style**: Ruff sauber? Typisierung korrekt?
4. **Architektur**: Passt es ins Rainbow-Modell?
5. **Doku**: Sind Docstrings da? README/CONTRIBUTING aktualisiert?

### Review-Feedback

Konstruktiv und direkt. Wir prangern Code an, nicht Menschen.

## Fragen?

Issues im Repo eroeffnen oder im Discord Channel fragen.
