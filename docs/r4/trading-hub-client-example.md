# trading-hub Client Beispiel (Rainbow)

## Umgebungsvariablen (empfohlen)

```bash
RAINBOW_BASE_URL=http://rainbow:8000
# Für Standalone-Tests lokal:
# RAINBOW_BASE_URL=http://localhost:18000
```

## Typische Aufrufe (Python-Beispiel)

```python
import httpx
import os

base = os.getenv("RAINBOW_BASE_URL", "http://rainbow:8000")

async def get_latest_signals(asset: str = None, limit: int = 50):
    params = {"limit": limit}
    if asset:
        params["asset"] = asset
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base}/signals/canonical/latest", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

async def get_health():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base}/health", timeout=5)
        return resp.json()
```

## Wichtige Regeln für den Client

- Bei `/health` != healthy oder Heartbeat-Datei stale → Source als `UNAVAILABLE` markieren.
- Nur `canonical` Endpoint für neue Signale verwenden.
- `data_quality.status` und `actionability` beachten.
- Bei Fehlern oder leeren Responses **keine** Trading-Entscheidungen treffen (fail-closed).

Siehe vollständigen Contract unter:
`ai4trade-bot/docs/integration/rainbow-signal-provider-contract.md`
