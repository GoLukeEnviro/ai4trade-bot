import json
import logging

from anthropic import Anthropic

from core.signal_model import Intent
import config

log = logging.getLogger(__name__)

ALLOWED_INTENTS = {
    "pause_pair",
    "resume_pair",
    "close_positions",
    "show_pnl",
    "status",
}

APPROVAL_REQUIRED_INTENTS = {"close_positions"}

COMMANDER_PROMPT = (
    "You are a trading bot command parser. Parse the user's message into a JSON intent.\n"
    f"Allowed intents: {', '.join(sorted(ALLOWED_INTENTS))}.\n"
    'Return ONLY JSON: {{"intent": "<intent>", "pair": "<PAIR/USDT>" or null, "requires_approval": true/false}}\n'
    "If no pair is mentioned, pair is null.\n"
    "close_positions requires approval.\n\n"
    "User message: {message}"
)


class Commander:
    def __init__(self, api_key: str | None = None):
        self._client = Anthropic(api_key=api_key or config.CLAUDE_API_KEY)

    def parse(self, user_input: str) -> Intent:
        try:
            response = self._client.messages.create(
                model=config.CLAUDE_MODEL,
                messages=[{"role": "user", "content": COMMANDER_PROMPT.format(message=user_input)}],
                max_tokens=150,
            )
            data = json.loads(response.content[0].text)
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
