import os
from dotenv import load_dotenv

load_dotenv()

AI4TRADE_TOKEN = os.getenv("AI4TRADE_TOKEN", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

TRADING_PAIRS = [p.strip() for p in os.getenv("TRADING_PAIRS", "BTC/USDT,ETH/USDT,SOL/USDT").split(",")]
DATA_INTERVAL = int(os.getenv("DATA_INTERVAL", "60"))
SENTIMENT_INTERVAL = int(os.getenv("SENTIMENT_INTERVAL", "300"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))

MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.10"))
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "0.20"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "3"))
CONFIDENCE_THRESHOLD = int(os.getenv("CONFIDENCE_THRESHOLD", "60"))

MODE = os.getenv("MODE", "dry_run")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MAX_SIGNAL_QUEUE = int(os.getenv("MAX_SIGNAL_QUEUE", "50"))

BINANCE_BASE = "https://api.binance.com"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
AI4TRADE_BASE = "https://ai4trade.ai/api"
CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com/data/v2"
