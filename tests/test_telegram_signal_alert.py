"""Tests für TelegramSignalAlert (Issue #92 — Compact Signal Summaries).

Die Tests fokussieren sich auf:
  * Priority-Gate (nur high/critical)
  * Cooldown per Asset (nicht global)
  * Kompaktes Nachrichtenformat inkl. summary-Feld
  * Graceful Degradation bei HTTP-Fehlern
  * Fehlende Konfiguration → kein Versand
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.signals.envelope import (
    CanonicalSignalEnvelope,
    DataQuality,
    DataQualityStatus,
    SignalClass,
    SignalDirection,
    SignalPriority,
)
from monitoring.alerts import TelegramSignalAlert


def _envelope(
    *,
    asset: str = "BTC/USDT:USDT",
    priority: SignalPriority = SignalPriority.HIGH,
    signal_class: SignalClass = SignalClass.ENTRY,
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float = 0.72,
    risk_score: float = 0.3,
) -> CanonicalSignalEnvelope:
    return CanonicalSignalEnvelope(
        signal_class=signal_class,
        subtype="test",
        source="test",
        asset=asset,
        direction=direction,
        confidence=confidence,
        risk_score=risk_score,
        priority=priority,
        data_quality=DataQuality(status=DataQualityStatus.OK),
        actionability={"can_alert": True},
        invalidation={"max_age_seconds": 3600, "conditions": []},
        raw_refs=[],
    )


class TestConstant:
    """Spec verlangt COOLDOWN_SECONDS = 300 als Klassenkonstante."""

    def test_class_constant_is_300(self) -> None:
        assert TelegramSignalAlert.COOLDOWN_SECONDS == 300


class TestShouldSendPriorityGate:
    """Nur high/critical dürfen gesendet werden."""

    def test_high_priority_passes(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        ok, reason = alert.should_send(_envelope(priority=SignalPriority.HIGH), now=0.0)
        assert ok is True
        assert reason == "ok"

    def test_critical_priority_passes(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        ok, reason = alert.should_send(_envelope(priority=SignalPriority.CRITICAL), now=0.0)
        assert ok is True
        assert reason == "ok"

    @pytest.mark.parametrize("priority", [SignalPriority.LOW, SignalPriority.MEDIUM])
    def test_below_threshold_blocked(self, priority: SignalPriority) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        ok, reason = alert.should_send(_envelope(priority=priority), now=0.0)
        assert ok is False
        assert "below_threshold" in reason


class TestShouldSendCooldown:
    """Cooldown ist per Asset, nicht global."""

    def test_first_send_passes(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        ok, _ = alert.should_send(_envelope(asset="BTC/USDT:USDT"), now=0.0)
        assert ok is True

    def test_second_send_within_cooldown_blocked(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        alert._last_sent["BTC/USDT:USDT"] = 100.0
        ok, reason = alert.should_send(_envelope(asset="BTC/USDT:USDT"), now=100.0 + 60.0)
        assert ok is False
        assert reason == "cooldown_active"

    def test_after_cooldown_passes(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        alert._last_sent["BTC/USDT:USDT"] = 100.0
        ok, _ = alert.should_send(_envelope(asset="BTC/USDT:USDT"), now=100.0 + 301.0)
        assert ok is True

    def test_cooldown_is_per_asset(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        alert._last_sent["BTC/USDT:USDT"] = 100.0
        # ETH darf trotzdem feuern obwohl BTC gerade gesendet hat
        ok, _ = alert.should_send(_envelope(asset="ETH/USDT:USDT"), now=100.0 + 10.0)
        assert ok is True

    def test_custom_cooldown_seconds(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid", cooldown_seconds=10.0)
        alert._last_sent["BTC/USDT:USDT"] = 100.0
        ok, _ = alert.should_send(_envelope(asset="BTC/USDT:USDT"), now=100.0 + 11.0)
        assert ok is True

    def test_should_send_has_no_side_effects(self) -> None:
        """should_send darf den Cooldown-State NICHT verändern."""
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        alert.should_send(_envelope(asset="BTC/USDT:USDT"), now=42.0)
        assert alert._last_sent == {}


class TestSendUnconfigured:
    """Ohne Token/Chat-ID wird nichts gesendet."""

    @pytest.mark.asyncio
    async def test_no_token_returns_false(self) -> None:
        alert = TelegramSignalAlert(bot_token=None, chat_id="cid")
        sent = await alert.send(_envelope(), "summary")
        assert sent is False

    @pytest.mark.asyncio
    async def test_no_chat_id_returns_false(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id=None)
        sent = await alert.send(_envelope(), "summary")
        assert sent is False


class TestSendRouting:
    """send() kombiniert priority/cooldown und ruft HTTP nur bei Erfolg auf."""

    @pytest.mark.asyncio
    async def test_low_priority_skips_http(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        with patch("monitoring.alerts.httpx.AsyncClient") as mock_client_cls:
            sent = await alert.send(_envelope(priority=SignalPriority.LOW), "summary")
            assert sent is False
            mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_cooldown_blocks_http(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")
        alert._last_sent["BTC/USDT:USDT"] = 100.0
        with patch("monitoring.alerts.httpx.AsyncClient") as mock_client_cls:
            sent = await alert.send(_envelope(), "summary", now=100.0 + 10.0)
            assert sent is False
            mock_client_cls.assert_not_called()


class TestSendHttpSuccess:
    """Erfolgreicher Versand aktualisiert den Cooldown-State."""

    @pytest.mark.asyncio
    async def test_successful_send_sets_cooldown(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("monitoring.alerts.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            sent = await alert.send(_envelope(asset="BTC/USDT:USDT"), "test summary", now=42.0)

        assert sent is True
        assert alert._last_sent["BTC/USDT:USDT"] == 42.0
        mock_client.post.assert_awaited_once()
        # URL muss den Token enthalten, Chat-ID im Payload
        posted_args = mock_client.post.await_args
        assert "tok" in posted_args.args[0]
        assert posted_args.kwargs["json"]["chat_id"] == "cid"

    @pytest.mark.asyncio
    async def test_http_error_returns_false(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPError("boom")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("monitoring.alerts.httpx.AsyncClient", return_value=mock_client):
            sent = await alert.send(_envelope(), "summary", now=0.0)

        assert sent is False
        # Bei HTTP-Fehler darf der Cooldown nicht gesetzt werden.
        assert alert._last_sent == {}

    @pytest.mark.asyncio
    async def test_request_exception_returns_false(self) -> None:
        alert = TelegramSignalAlert(bot_token="tok", chat_id="cid")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("dns"))

        with patch("monitoring.alerts.httpx.AsyncClient", return_value=mock_client):
            sent = await alert.send(_envelope(), "summary", now=0.0)

        assert sent is False


class TestMessageFormat:
    """Die erzeugte Nachricht muss compact und sicher sein."""

    def test_includes_summary_field(self) -> None:
        env = _envelope(priority=SignalPriority.HIGH)
        msg = TelegramSignalAlert._format_message(env, "RSI oversold + volume spike")
        assert "RSI oversold + volume spike" in msg
        assert "Summary" in msg

    def test_includes_asset_and_priority(self) -> None:
        env = _envelope(asset="ETH/USDT:USDT", priority=SignalPriority.CRITICAL)
        msg = TelegramSignalAlert._format_message(env, "x")
        assert "ETH/USDT:USDT" in msg
        assert "CRITICAL" in msg

    def test_includes_direction_and_class(self) -> None:
        env = _envelope(
            signal_class=SignalClass.EXIT,
            direction=SignalDirection.BEARISH,
        )
        msg = TelegramSignalAlert._format_message(env, "x")
        assert "EXIT" in msg
        assert "BEARISH" in msg

    def test_includes_confidence_and_risk(self) -> None:
        env = _envelope(confidence=0.81, risk_score=0.42)
        msg = TelegramSignalAlert._format_message(env, "x")
        assert "0.81" in msg
        assert "0.42" in msg

    def test_advisory_marker_present(self) -> None:
        env = _envelope()
        msg = TelegramSignalAlert._format_message(env, "x")
        assert "advisory only" in msg.lower()

    def test_summary_html_escaped(self) -> None:
        env = _envelope()
        msg = TelegramSignalAlert._format_message(env, "<script>alert('x')</script>")
        assert "<script>" not in msg
        assert "&lt;script&gt;" in msg

    def test_critical_emoji(self) -> None:
        env = _envelope(priority=SignalPriority.CRITICAL)
        msg = TelegramSignalAlert._format_message(env, "x")
        assert "🔴" in msg

    def test_high_emoji(self) -> None:
        env = _envelope(priority=SignalPriority.HIGH)
        msg = TelegramSignalAlert._format_message(env, "x")
        assert "🟠" in msg
