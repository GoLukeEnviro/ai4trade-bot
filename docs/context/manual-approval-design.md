# Manual Approval -- Externalisierungs-Design

**Status:** MVP implementiert (Phase 4.5), Erweiterung geplant
**Datum:** 2026-05-29
**Geltungsbereich:** AI4Trade Bot -- Manuelle Freigabe vor Order-Ausfuehrung

---

## 1. Uebersicht

Manual Approval ist eine Policy im Safety Gateway, die eine manuelle Freigabe vor der Order-Ausfuehrung erfordert. Im MVP erfolgt die Freigabe ueber STDIN. Zukuenftige Erweiterungen sollen externe Approval-Kanaele unterstuetzen.

---

## 2. Aktuelle Implementierung

### Policy (`trading/policies/manual_approval.py`)

```python
class ManualApprovalPolicy(Policy):
    def check(self, signal, context: dict) -> PolicyResult:
        # dry_run: Approval nicht erforderlich
        # Live: context["approved"] muss True sein
```

### Verhalten

| Mode | Verhalten |
|------|-----------|
| `dry_run` | Approval nicht erforderlich, Policy passt |
| `live` | `context["approved"]` muss `True` sein, sonst BLOCK |

### STDIN-Flow (MVP)

```
Signal generiert -> Safety Gateway -> ManualApproval Policy
                                          |
                                    Live-Mode? -> Ja -> STDIN "Approve? [y/N]"
                                                          |
                                                      User-Eingabe
                                                          |
                                                   approved=True/False
```

---

## 3. Zukuenftige Approval-Methoden

### 3.1 Signed Approval

- Kryptographisch signierte Approval-Nachricht
- Schluessel des Administrators hinterlegt
- Kein STDIN, keine Interaktion am Terminal

### 3.2 TOTP-Token

- Zeitbasierter One-Time-Password
- Aehnlich 2FA (`core/two_factor.py`)
- Approval durch Eingabe eines gueltigen TOTP-Codes

### 3.3 Discord/Telegram Approval

```
Bot -> "Signal XYZ: BUY BTCUSDT $95,000. Approve?"
User -> "/approve XYZ"  (oder "/reject XYZ")
Bot -> Execution fortsetzen
```

- Asynchron, kein Terminal erforderlich
- Bot sendet Notification, wartet auf Response
- Timeout: Signal wird abgelehnt nach konfigurierbarer Zeit

### 3.4 Hardware Key

- FIDO2/WebAuthn Challenge-Response
- Physischer Sicherheitsschluessel erforderlich
- Hoechste Sicherheitsstufe fuer Live-Modus

---

## 4. Approval-Flow Architektur

```
User -> Approval Service -> Safety Gateway -> Execution
          |
          +-- STDIN (MVP)
          +-- TOTP
          +-- Discord/Telegram
          +-- Hardware Key
```

### Interface (zukuenftig)

```python
class ApprovalProvider(Protocol):
    def request_approval(self, signal: Signal) -> bool: ...
```

Jede Methode implementiert dieses Interface. Die Policy delegiert an den konfigurierten Provider.

---

## 5. Sicherheitsaspekte

- Approval gilt nur fuer ein einzelnes Signal, nicht fuer eine Session
- Timeout: Kein Approval nach konfigurierbarer Zeit = automatische Ablehnung
- Audit: Jede Approval-Entscheidung wird geloggt (akzeptiert, abgelehnt, abgelaufen)
- Rate-Limit: Approval-Requests koennen pro Zeiteinheit begrenzt werden

---

## 6. Referenzen

- Policy: `trading/policies/manual_approval.py`
- Safety Gateway: `trading/safety_gateway.py`
- 2FA (Referenz): `core/two_factor.py`
- Architektur-Doku: `docs/context/bitget-mcp-hybrid-architecture.md`

---

## 7. Aenderungshistorie

| Datum | Aenderung | Phase |
|-------|-----------|-------|
| 2026-05-29 | Design-Dokumentation | 4.5 |
