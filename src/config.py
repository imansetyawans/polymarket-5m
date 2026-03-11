"""
Configuration loader — reads .env and provides typed settings.
Validation is deferred to allow dry-run mode without credentials.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()


# ── Polymarket Auth (may be empty in dry-run) ────────────────────
POLY_PRIVATE_KEY: str = os.getenv("POLY_PRIVATE_KEY", "")
POLY_FUNDER_ADDRESS: str = os.getenv("POLY_FUNDER_ADDRESS", "")
CHAIN_ID: int = 137  # Polygon Mainnet
SIGNATURE_TYPE: int = int(os.getenv("SIGNATURE_TYPE", "2"))  # 0 = EOA, 2 = Polymarket Proxy

# ── API Hosts ────────────────────────────────────────────────────
CLOB_HOST: str = "https://clob.polymarket.com"
GAMMA_API_HOST: str = "https://gamma-api.polymarket.com"
BINANCE_BTC_URL: str = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
POLYGON_RPC_URL: str = os.getenv("POLYGON_RPC_URL", "")

# ── Quantitative Strategy Settings ───────────────────────────────
EDGE_THRESHOLD: float = float(os.getenv("EDGE_THRESHOLD", "0.07"))
KELLY_FRACTION: float = float(os.getenv("KELLY_FRACTION", "0.5"))
BTC_VOLATILITY_PER_SEC: float = float(os.getenv("BTC_VOLATILITY_PER_SEC", "2.50"))
ENTRY_SECONDS_BEFORE_CLOSE: float = float(os.getenv("ENTRY_SECONDS_BEFORE_CLOSE", "3.0"))
PRE_CLOSE_SELL_SECONDS: float = float(os.getenv("PRE_CLOSE_SELL_SECONDS", "0.7"))
GAP_TRIGGER_PERCENT: float = float(os.getenv("GAP_TRIGGER_PERCENT", "0.0006"))

# ── Contract Addresses (Polygon) ────────────────────────────────
USDC_ADDRESS: str = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CONDITIONAL_TOKENS_ADDRESS: str = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
EXCHANGE_ADDRESS: str = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE_ADDRESS: str = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
NEG_RISK_ADAPTER_ADDRESS: str = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

# ── Timing ───────────────────────────────────────────────────────
DASHBOARD_REFRESH_PER_SECOND: int = 1  # 500ms
POSITION_POLL_INTERVAL: int = 1  # seconds
MARKET_RETRY_INTERVAL: int = 1  # seconds when idle
PRICE_FEED_INTERVAL: float = 1.0  # seconds

# ── Cooldown ─────────────────────────────────────────────────────
COOLDOWN_START_TIME: str = os.getenv("COOLDOWN_START_TIME", "10:00")
COOLDOWN_END_TIME: str = os.getenv("COOLDOWN_END_TIME", "11:59")
COOLDOWN_TIMEZONE: str = os.getenv("COOLDOWN_TIMEZONE", "US/Eastern")


def validate_trading_config() -> None:
    """
    Validate that required credentials are present.
    Call this before starting any trading operations (not during dry-run).
    """
    missing = []
    if not POLY_PRIVATE_KEY:
        missing.append("POLY_PRIVATE_KEY")
    if not POLY_FUNDER_ADDRESS:
        missing.append("POLY_FUNDER_ADDRESS")

    if missing:
        print(f"[ERROR] Missing required env var(s): {', '.join(missing)}")
        print(f"        Copy .env.example → .env and fill in your values.")
        sys.exit(1)
