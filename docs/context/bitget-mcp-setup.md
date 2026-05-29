# Bitget MCP Read-Only Setup

**Status:** Phase 3.1
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- MCP-Integration fuer read-only Marktdaten

---

## 1. Uebersicht

Das Model Context Protocol (MCP) dient als **read-only Operations-Layer** fuer KI-Agenten, um auf Bitget-Marktdaten zuzugreifen. MCP ist vollstaendig unabhaengig von der Trading-Loop des AI4Trade Bot und hat keinen Einfluss auf die Signalerzeugung oder Order-Ausfuehrung.

### Zweck

- KI-Agenten koennen Marktdaten in Echtzeit abfragen (Preise, Orderbooks, Charts)
- MCP dient ausschliesslich der **Informationsbeschaffung** -- niemals der Handelsausfuehrung
- Die Trading-Loop bleibt voll funktionsfaehig, auch wenn MCP nicht verfuegbar ist

### Harte Regel

> **MCP DARF NIEMALS direkt Orders ausfuehren.**
> MCP hat keinen Zugriff auf das Trading-Modul. Es gibt keinen Execution-Pfad ueber MCP.
> Diese Regel ist architektonisch durchgesetzt, nicht nur durch Konvention.

---

## 2. Installation

Der Bitget MCP Server wird via npx ausgefuehrt. Kein globaler Install erforderlich.

```bash
npx -y bitget-mcp-server --modules market
```

### Voraussetzungen

- Node.js 18+ (fuer npx)
- Keine API-Keys fuer reine Marktdaten erforderlich
- Netzwerkzugang zu Bitget REST API

---

## 3. Konfiguration

Die Beispiel-Konfiguration liegt unter:
`config/examples/mcp.bitget.readonly.example.json`

Siehe dort fuer die vollstaendige JSON-Konfiguration. Wesentliche Punkte:

- **Module:** Nur `market` -- kein `trade`, kein `account`
- **API-Keys:** Fuer reine Marktdaten leer (nicht erforderlich)
- **Server-Name:** `bitget-market` -- klar als read-only gekennzeichnet

---

## 4. Erlaubte Operationen (Market Module Only)

Das `market`-Modul beschraenkt MCP auf folgende Operationen:

| Operation | Beschreibung | Risk-Level |
|-----------|-------------|------------|
| Marktpreise abfragen | Aktuelle Spot/Ticker-Preise | Read-only |
| OHLCV/Candle-Daten lesen | Historische und aktuelle Kerzendaten | Read-only |
| Orderbook einsehen | Aktuelle Ask/Bid-Levels | Read-only |
| Ticker-Daten lesen | 24h-Volume, High/Low, Bestandesaenderung | Read-only |

Alle Operationen sind reine Lesezugriffe. Es werden keine Daten an Bitget gesendet.

---

## 5. Verbotene Operationen

Die folgenden Operationen sind durch das `--modules market` Flag und die Architektur ausgeschlossen:

| Kategorie | Operation | Status |
|-----------|-----------|--------|
| **Orders** | Erstellen, Aendern, Stornieren | BLOCKIERT |
| **Positions** | Oeffnen, Schliessen, Aendern | BLOCKIERT |
| **Account** | Balances abfragen, Kontoinfos | BLOCKIERT |
| **Trading** | Alle Trade-Modul-Endpunkte | BLOCKIERT |
| **Withdrawals** | Auszahlungen, Transfers | BLOCKIERT |

Selbst wenn API-Keys konfiguriert waeren: Das `--modules market` Flag laedt keine Trade- oder Account-Endpunkte. Der MCP-Server hat physisch keine Faehigkeit, Orders zu platzieren.

---

## 6. Sandbox-Regeln (Phase 6.3)

Diese Regeln gelten fuer die spaetere Sandbox-Phase und sind hier vorab dokumentiert.

### MCP bekommt NIEMALS

- **Direkter Datenbank-Zugriff** -- MCP kommuniziert nur ueber definierte REST-APIs
- **Execution-Zugriff** -- Kein Pfad zu Order-Endpunkten, keine Ausnahme
- **Secret-Zugriff** -- API-Keys werden ueber Umgebungsvariablen injiziert, nie direkt uebergeben

### MCP bekommt NUR

- **Abstrahierte Read-Only-Tools** -- Marktdaten ueber standardisierte MCP-Tool-Schnittstellen
- **Kontrollierte Aktionen ueber Safety Gateway** -- Jede Aktion muss durch das Safety Gateway validiert werden

### Unabhaengigkeit

- Die Trading-Loop des AI4Trade Bot bleibt **unabhaengig** von MCP-Verfuegbarkeit
- MCP-Ausfall hat keinen Einfluss auf die Signalerzeugung
- MCP ist ein optionales Tool fuer Agenten-Interaktion, keine Kernkomponente

---

## 7. Architektur-Fluss

```
+-----------+     +--------+     +---------------+     +---------------+     +--------+
| KI-Agent  | --> |  MCP   | --> | Safety Gate   | --> | REST Executor | --> | Bitget |
| (Claude)  |     | Server |     | (Validierung) |     | (HTTP-Call)   |     |  API   |
+-----------+     +--------+     +---------------+     +---------------+     +--------+
                                       |
                                       v
                              +------------------+
                              | Intent-Check:    |
                              | - Nur read-only? |
                              | - Kein Trade?    |
                              | - Kein Account?  |
                              +------------------+
```

### Fluss-Erklaerung

1. **KI-Agent** stellt Anfrage ueber MCP-Tool
2. **MCP Server** (market-Modul) reicht Anfrage weiter
3. **Safety Gateway** validiert: Nur read-only Operationen erlaubt
4. **REST Executor** fueert HTTP-Call gegen Bitget API aus
5. **Bitget API** liefert Marktdaten zurueck

Jeder Schritt im Fluss ist so konzipiert, dass ein Fehlverhalten im vorherigen Schritt keine Auswirkungen auf nachfolgende Schritte hat. Selbst bei MCP-Kompromittierung bleibt der Trading-Kanal geschuetzt.

---

## 8. Troubleshooting

### MCP-Server startet nicht

**Symptom:** `npx bitget-mcp-server` schlaegt fehl

**Ursachen und Loesungen:**

| Ursache | Loesung |
|---------|---------|
| Node.js nicht installiert | Node.js 18+ installieren: `node --version` pruefen |
| npx nicht verfuegbar | npm installieren (enthaelt npx) |
| Netzwerk-Probleme | Bitget API Erreichbarkeit pruefen: `curl https://api.bitget.com/api/v2/public/time` |
| Modul nicht gefunden | `--modules market` Schreibweise pruefen |

### Keine Marktdaten

**Symptom:** MCP-Tool liefert leere Ergebnisse oder Fehler

**Pruefschritte:**

1. Bitget API Status pruefen: `https://api.bitget.com/api/v2/public/time`
2. Trading-Pair-Format validieren (z.B. `BTCUSDT` nicht `BTC/USDT`)
3. Zeitraum-Parameter fuer OHLCV pruefen (gueltige Intervalle: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`)

### Rate Limiting

**Symptom:** HTTP 429 Fehler

**Loesung:** Bitget oeffentliche API erlaubt ca. 20 Requests/Sekunde. Bei haeufigen Abfragen:
- Intervalle zwischen Abfragen erhoehen
- Caching auf Agenten-Seite implementieren
- Mehrere Trading-Pairs bündeln falls moeglich

### MCP in Claude Desktop nicht sichtbar

**Symptom:** MCP-Tools erscheinen nicht in Claude

**Pruefschritte:**

1. Konfigurationsdatei im korrekten Verzeichnis platzieren
2. JSON-Syntax validieren
3. Claude Desktop neu starten nach Konfigurationsaenderung
4. Server-Name eindeutig halten (`bitget-market`, nicht `bitget`)

---

## 9. Referenzen

- Beispiel-Konfiguration: `config/examples/mcp.bitget.readonly.example.json`
- Projekt-README: `README.md`
- Design-Spec: `docs/superpowers/specs/2026-05-07-ai4trade-bot-design.md`
- Bitget API Docs: `https://www.bitget.com/api-doc/common/introduction`

---

## 10. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Initiale Erstellung | 3.1 |
