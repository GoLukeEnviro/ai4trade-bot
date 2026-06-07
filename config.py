import os

from dotenv import load_dotenv

load_dotenv()

from core.secret_provider import create_secret_provider  # noqa: E402

_secret_provider = create_secret_provider()

# Secrets loaded through provider
AI4TRADE_TOKEN = _secret_provider.get("AI4TRADE_TOKEN")
CLAUDE_API_KEY = _secret_provider.get("CLAUDE_API_KEY")
LLM_API_KEY = _secret_provider.get("LLM_API_KEY")

# Non-secret config stays with os.getenv
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")

ASSETS = [p.strip() for p in os.getenv("ASSETS", "BTC/USDT,ETH/USDT,SOL/USDT").split(",")]
DATA_INTERVAL = int(os.getenv("DATA_INTERVAL", "60"))
SENTIMENT_INTERVAL = int(os.getenv("SENTIMENT_INTERVAL", "300"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "30"))

CONFIDENCE_THRESHOLD = int(os.getenv("CONFIDENCE_THRESHOLD", "60"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")
MAX_SIGNAL_QUEUE = int(os.getenv("MAX_SIGNAL_QUEUE", "50"))
DB_PATH = os.getenv("DB_PATH", "storage/bot.db")

RATE_LIMIT_BITGET = float(os.getenv("RATE_LIMIT_BITGET", "10"))
RATE_LIMIT_COINGECKO = float(os.getenv("RATE_LIMIT_COINGECKO", "5"))
RATE_LIMIT_AI4TRADE = float(os.getenv("RATE_LIMIT_AI4TRADE", "2"))
RATE_LIMIT_CRYPTOCOMPARE = float(os.getenv("RATE_LIMIT_CRYPTOCOMPARE", "5"))
RATE_LIMIT_LLM = float(os.getenv("RATE_LIMIT_LLM", "1"))

BITGET_BASE = "https://api.bitget.com"
EXCHANGE_PROVIDER = os.getenv("EXCHANGE_PROVIDER", "bitget")
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
AI4TRADE_BASE = "https://ai4trade.ai/api"
CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com/data/v2"

METRICS_PORT = int(os.getenv("METRICS_PORT", "9090"))

# Rainbow Engine integration
RAINBOW_API_URL = os.getenv("RAINBOW_API_URL", "http://localhost:8000")

# DeepSeek AI Evaluation
DEEPSEEK_API_KEY = _secret_provider.get("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
