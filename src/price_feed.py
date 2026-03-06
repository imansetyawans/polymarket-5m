"""
Live BTC price feed — reads from Chainlink BTC/USD oracle on Polygon.
This is the same data source Polymarket uses for btc-updown-5m resolution.
"""

import logging
import asyncio
from typing import Optional

from web3 import Web3
from src import config

log = logging.getLogger("polybot")

# Chainlink BTC/USD Price Feed on Polygon Mainnet
CHAINLINK_BTC_USD = "0xc907E116054Ad103354f2D350FD2514433D57F6f"

# Minimal ABI for Chainlink Aggregator V3
CHAINLINK_ABI = [
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Public Polygon RPCs (fallback order)
POLYGON_RPCS = [
    "https://polygon.drpc.org",
    "https://polygon-bor-rpc.publicnode.com",
]

# Module-level cached connection
_w3: Optional[Web3] = None
_contract = None
_decimals: Optional[int] = None


def _get_connection():
    """Get or create a cached web3 connection and contract."""
    global _w3, _contract, _decimals

    if _w3 and _w3.is_connected() and _contract:
        return _w3, _contract, _decimals

    for rpc in POLYGON_RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
            if w3.is_connected():
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(CHAINLINK_BTC_USD),
                    abi=CHAINLINK_ABI,
                )
                decimals = contract.functions.decimals().call()
                _w3 = w3
                _contract = contract
                _decimals = decimals
                log.info("Chainlink feed connected via %s", rpc)
                return w3, contract, decimals
        except Exception as e:
            log.debug("RPC %s failed: %s", rpc, e)
            continue

    return None, None, None


def fetch_btc_price_sync() -> Optional[float]:
    """Synchronous Chainlink BTC/USD price read (called from async via executor)."""
    try:
        w3, contract, decimals = _get_connection()
        if not contract:
            return None

        data = contract.functions.latestRoundData().call()
        price = data[1] / (10 ** decimals)
        return price if price > 0 else None
    except Exception as e:
        log.warning("Chainlink BTC/USD read failed: %s", e)
        # Reset connection so it retries next time
        global _w3, _contract
        _w3 = None
        _contract = None
        return None


async def price_feed_loop(state: dict) -> None:
    """
    Continuous loop that keeps state["btc_price"] updated with the latest
    BTC/USD price from Chainlink oracle on Polygon (same source as Polymarket).
    """
    loop = asyncio.get_event_loop()

    # Initial fetch with visible logging
    log.info("Starting Chainlink BTC/USD price feed...")
    try:
        price = await loop.run_in_executor(None, fetch_btc_price_sync)
        if price is not None:
            state["btc_price"] = price
            log.info("Initial BTC price: $%.2f", price)
        else:
            log.warning("Initial BTC price fetch failed — will retry")
    except Exception as e:
        log.warning("Initial price feed error: %s", e)

    # Continuous polling every 1s
    while True:
        await asyncio.sleep(1)
        try:
            price = await loop.run_in_executor(None, fetch_btc_price_sync)
            if price is not None:
                state["btc_price"] = price
        except Exception as e:
            log.warning("Price feed error: %s", e)
