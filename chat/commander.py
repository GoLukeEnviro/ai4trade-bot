import json
import logging

from ai.providers import LLMProvider, create_provider
from core.signal_model import Intent

log = logging.getLogger(__name__)

ALLOWED_INTENTS = {
    "pause_pair",
    "resume_pair",
    "close_positions",
    "show_pnl",
    "status",
    "set_strategy",
    "set_risk_level",
    "show_performance",
    "toggle_shadow_mode",
    "show_audit_log",
}

APPROVAL_REQUIRED_INTENTS = {"close_positions", "set_risk_level", "toggle_shadow_mode"}

COMMANDER_PROMPT = (
    "You are a trading bot command parser. Parse the user's message into a JSON intent.\n"
    f"Allowed intents: {', '.join(sorted(ALLOWED_INTENTS))}.\n"
    'Return ONLY JSON: {{"intent": "<intent>", "pair": "<PAIR/USDT>" or null, "requires_approval": true/false}}\n'
    "If no pair is mentioned, pair is null.\n"
    "Intents requiring approval: close_positions, set_risk_level, toggle_shadow_mode.\n\n"
    "Intent descriptions:\n"
    "- pause_pair: Pause trading for a specific pair\n"
    "- resume_pair: Resume trading for a specific pair\n"
    "- close_positions: Close all positions (pair optional)\n"
    "- show_pnl: Show profit and loss overview\n"
    "- status: Show general bot status\n"
    "- set_strategy: Switch to a different trading strategy\n"
    "- set_risk_level: Change risk level (conservative/normal/aggressive)\n"
    "- show_performance: Show performance statistics\n"
    "- toggle_shadow_mode: Enable or disable shadow mode\n"
    "- show_audit_log: Show recent audit log entries\n\n"
    "User message: {message}"
)


class Commander:
    def __init__(self, api_key: str | None = None):
        self._llm: LLMProvider = create_provider(api_key=api_key)

    def parse(self, user_input: str) -> Intent:
        try:
            text = self._llm.complete(COMMANDER_PROMPT.format(message=user_input), max_tokens=150)
            data = json.loads(text)
            intent_name = data.get("intent", "unknown")

            if intent_name not in ALLOWED_INTENTS:
                log.warning(f"Blockierter Intent: {intent_name}")
                return Intent(intent="unknown", pair=None, requires_approval=False)

            pair = data.get("pair")
            requires_approval = data.get("requires_approval", False)

            if intent_name in APPROVAL_REQUIRED_INTENTS:
                requires_approval = True

            return Intent(intent=intent_name, pair=pair, requires_approval=requires_approval)
        except Exception as e:
            log.error(f"Command-Parsing fehlgeschlagen: {e}")
            return Intent(intent="unknown", pair=None, requires_approval=False)
