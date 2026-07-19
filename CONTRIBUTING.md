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

---

## Workflow-Konventionen

### Branch-Naming

Branches folgen diesem Schema:

- `feat/<ticket>-<kurzbeschreibung>` — Neue Features (z.B. `feat/99-telegram-collector`)
- `fix/<ticket>-<kurzbeschreibung>` — Bugfixes (z.B. `fix/42-rate-limiter-crash`)
- `refactor/<kurzbeschreibung>` — Code-Refactorings (z.B. `refactor/cleanup-ta-module`)

### Commit-Style

**Format:** `<type>: <kurzbeschreibung>`

**Types:**
- `feat` — Neue Features
- `fix` — Bugfixes
- `refactor` — Code-Umstrukturierung ohne Behavior-Änderung
- `test` — Neue Tests oder Test-Fixes
- `docs` — Dokumentation
- `chore` — Build, Dependencies, Config
- `style` — Formatierung, Linting
- `perf` — Performance-Optimierung

**Sprache:** Deutsch

**Fokus:** **Warum**, nicht Was. Der Diff zeigt das "Was", der Commit erklärt das "Warum".

**Beispiele:**
```bash
feat: telegram collector mit channel-filtering
fix: rate limiter crash bei ungültigem token
refactor: ta collector duplikation entfernen
test: rainbow scorer mit cross-confirmation abdecken
docs: readme mit secret-setup ergänzen
```

### Test-Requirements

**Pflicht:**
- **Neue Features MÜSSEN Tests haben** — mindestens ein Unit-Test pro neuer Funktion/Klasse
- **Bugfixes MÜSSEN einen Test enthalten der den Bug reproduziert** — bevor der Fix implementiert wird
- **Vor jedem Commit: relevante Tests ausführen** — nicht blind committen

**Test-Befehl:**
```bash
# Alle Tests (Windows)
& .\.venv\Scripts\python.exe -m pytest tests/ -q

# Spezifischer Test
pytest rainbow/tests/test_models.py -v

# Mit Coverage
pytest rainbow/tests/ tests/evaluation/ tests/core/ --cov=rainbow --cov-report=term
```

**Was NICHT getestet wird:**
- Triviale Getter/Setter ohne Logik
- Framework-Interna (FastAPI, SQLite-Interna)
- UI-Rendering ohne Business-Logik

### Pre-Commit Hooks

**Installation (nach Clone/Pull):**
```bash
pre-commit install
```

**Was macht der Hook:**
- `ruff check` — Linting (Code-Quality-Checks)
- `ruff format` — Code-Formatierung
- `bandit` — Security-Checks (SQL-Injection, Secrets in Code, etc.)

**Bei Hook-Fehlern:**
- **NIEMALS `--no-verify` verwenden** — Fehler beheben, nicht umgehen
- Bei Unklarheit: Issue öffnen oder im PR diskutieren

### Pull Request-Prozess

**Vor PR-Erstellung:**
1. Tests laufen grün lokal
2. Pre-Commit-Hooks laufen grün
3. Branch ist auf `main` rebased (keine Merge-Konflikte)

**PR-Anforderungen:**
- **Titel:** < 70 Zeichen, klar und prägnant
- **Summary:** 1-3 Bulletpoints mit:
  - Was wurde geändert (kurz)
  - Warum (Kontext, Issue-Link)
  - Verifikation (wie wurde getestet)
- **Code-Review erforderlich:** Mindestens 1 Approval bevor Merge

**Beispiel-PR-Template:**
```markdown
## Änderungen
- Telegram Collector mit Channel-Filtering implementiert (#99)
- Rate-Limiter für Telegram Bot API hinzugefügt

## Warum
Telegram ist eine wichtige Social-Signal-Quelle. Issue #99 forderte Channel-basiertes Filtering.

## Verifikation
- Unit-Tests: `pytest rainbow/tests/test_telegram_collector.py` (5 Tests, alle grün)
- Integration-Test: Collector läuft 10 Minuten gegen Testkanal, 47 Signale gesammelt
- Rate-Limiter verhindert 429-Errors (3 Aufrufe/Sekunde)
```

---

## Fragen?

Bei Unklarheiten:
- Issue öffnen mit Label `question`
- Im PR diskutieren
- README.md und docs/ durchsuchen
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
