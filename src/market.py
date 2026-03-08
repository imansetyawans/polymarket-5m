"""
Market discovery — find the active BTC btc-updown-5m window via Gamma API.

The slug format is: btc-updown-5m-{unix_timestamp}
where the timestamp is the START time of the 5-minute window (aligned to 5m boundaries).

We compute candidate timestamps around the current time and query the events endpoint
to find active (non-closed) windows.
"""

import logging
import asyncio
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List
import json

import aiohttp
from web3 import Web3
from src import config

log = logging.getLogger("polybot")

WINDOW_DURATION = 300  # 5 minutes in seconds

# --- Chainlink Oracle Fallback Configuration ---
CHAINLINK_BTC_USD = "0xc907E116054Ad103354f2D350FD2514433D57F6f"

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
        "inputs": [{"name": "_roundId", "type": "uint80"}],
        "name": "getRoundData",
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

POLYGON_RPCS = [
    "https://polygon.drpc.org",
    "https://polygon-bor-rpc.publicnode.com",
]

def fetch_chainlink_btc_sync() -> Optional[float]:
    """Synchronous Chainlink BTC/USD price read for precise PriceToBeat fallbacks."""
    for rpc in POLYGON_RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 5}))
            if w3.is_connected():
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(CHAINLINK_BTC_USD),
                    abi=CHAINLINK_ABI,
                )
                decimals = contract.functions.decimals().call()
                data = contract.functions.latestRoundData().call()
                price = data[1] / (10 ** decimals)
                return price if price > 0 else None
        except Exception as e:
            log.debug("Chainlink RPC %s failed: %s", rpc, e)
            continue
    return None

def fetch_historical_chainlink_btc_sync(target_ts: int) -> Optional[float]:
    """
    Synchronously fetches the exact Chainlink BTC/USD price at or immediately preceding target_ts.
    It linear-searches backwards from latestRoundData to perfectly match the Polymarket start strike.
    """
    for rpc in POLYGON_RPCS:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 5}))
            if w3.is_connected():
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(CHAINLINK_BTC_USD),
                    abi=CHAINLINK_ABI,
                )
                decimals = contract.functions.decimals().call()
                latest = contract.functions.latestRoundData().call()
                round_id = latest[0]
                
                # Search backwards for up to 300 rounds
                for i in range(300):
                    data = contract.functions.getRoundData(round_id - i).call()
                    up_ts = data[3]
                    price = data[1] / (10 ** decimals)
                    if up_ts <= target_ts:
                        return price
        except Exception as e:
            log.debug("Historical Chainlink RPC %s failed: %s", rpc, e)
            continue
    return None


@dataclass
class MarketWindow:
    """Represents an active btc-updown-5m market window."""
    condition_id: str
    question_id: str
    slug: str
    start_date: datetime       # UTC start of window
    end_date: datetime         # UTC close time
    price_to_beat: float       # from eventMetadata.priceToBeat
    up_token_id: str
    down_token_id: str
    neg_risk: bool
    market_id: str             # Gamma market ID
    accepting_orders: bool


def _get_candidate_timestamps(now_utc: datetime) -> List[int]:
    """
    Generate candidate 5-minute window start timestamps around the current time.
    Returns timestamps for: current window, next window, and previous window.
    """
    now_ts = int(now_utc.timestamp())
    # Align to 5-minute boundary
    current_window_start = (now_ts // WINDOW_DURATION) * WINDOW_DURATION
    return [
        current_window_start,
        current_window_start + WINDOW_DURATION,   # next window
        current_window_start - WINDOW_DURATION,   # previous window (may still be open)
    ]


def _parse_event_to_window(event: dict) -> Optional[MarketWindow]:
    """Parse a Gamma API event response into a MarketWindow."""
    try:
        markets = event.get("markets", [])
        if not markets:
            return None

        mkt = markets[0]  # Each event has exactly one market

        # Parse end date
        end_str = mkt.get("endDate", "")
        if not end_str:
            return None
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

        # Parse start time (eventStartTime on the market, or startTime on the event)
        start_str = mkt.get("eventStartTime", event.get("startTime", ""))
        if start_str:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        else:
            # Fallback: endDate - 5 minutes
            from datetime import timedelta
            start_dt = end_dt - timedelta(seconds=WINDOW_DURATION)

        # Price to beat from eventMetadata
        event_metadata = event.get("eventMetadata", {})
        price_to_beat = float(event_metadata.get("priceToBeat", 0))

        # Token IDs from clobTokenIds (JSON string)
        clob_ids_raw = mkt.get("clobTokenIds", "[]")
        if isinstance(clob_ids_raw, str):
            clob_ids = json.loads(clob_ids_raw)
        else:
            clob_ids = clob_ids_raw

        if len(clob_ids) < 2:
            log.warning("Market %s has < 2 token IDs", mkt.get("slug"))
            return None

        # Outcomes — determine which token is Up vs Down
        outcomes_raw = mkt.get("outcomes", "[]")
        if isinstance(outcomes_raw, str):
            outcomes = json.loads(outcomes_raw)
        else:
            outcomes = outcomes_raw

        up_token = clob_ids[0]
        down_token = clob_ids[1]

        # Map by outcome name
        for i, outcome in enumerate(outcomes):
            name = outcome.lower() if isinstance(outcome, str) else ""
            if "up" in name and i < len(clob_ids):
                up_token = clob_ids[i]
            elif "down" in name and i < len(clob_ids):
                down_token = clob_ids[i]

        return MarketWindow(
            condition_id=mkt.get("conditionId", ""),
            question_id=mkt.get("questionID", ""),
            slug=mkt.get("slug", event.get("slug", "")),
            start_date=start_dt,
            end_date=end_dt,
            price_to_beat=price_to_beat,
            up_token_id=up_token,
            down_token_id=down_token,
            neg_risk=bool(mkt.get("negRisk", False)),
            market_id=str(mkt.get("id", "")),
            accepting_orders=bool(mkt.get("acceptingOrders", False)),
        )

    except Exception as e:
        log.error("Failed to parse event: %s", e)
        return None



async def fetch_active_window(session: aiohttp.ClientSession) -> Optional[MarketWindow]:
    """
    Find the current active btc-updown-5m window by computing candidate
    timestamps and querying the Gamma events API.
    """
    now = datetime.now(timezone.utc)
    candidates = _get_candidate_timestamps(now)

    for ts in candidates:
        slug = f"btc-updown-5m-{ts}"
        try:
            url = f"{config.GAMMA_API_HOST}/events"
            async with session.get(url, params={"slug": slug}) as resp:
                if resp.status != 200:
                    continue
                events = await resp.json()

            if not events:
                continue

            event = events[0]

            # Skip closed events
            if event.get("closed", False):
                continue

            window = _parse_event_to_window(event)
            if not window:
                continue

            # Check if window is still in the future or currently active
            if window.end_date <= now:
                continue

            return window

        except Exception as e:
            log.debug("Error fetching slug %s: %s", slug, e)
            continue

    return None


async def market_discovery_loop(state: dict) -> None:
    """
    Continuous loop that keeps state["window"] updated with the current active
    MarketWindow, or None when idle.

    priceToBeat comes from the PREVIOUS window's eventMetadata.priceToBeat
    (populated by Gamma API after that window resolves). This matches exactly
    what Polymarket displays as "Price to beat" on the frontend.

    The loop keeps re-querying until the value appears (may take a few seconds
    after a new window starts).
    """
    async with aiohttp.ClientSession() as session:
        while True:
            window = await fetch_active_window(session)
            old = state.get("window")

            if window:
                # Only log when we switch to a new window
                if not old or old.slug != window.slug:
                    log.info(
                        "Active window: %s | closes %s UTC",
                        window.slug,
                        window.end_date.strftime("%H:%M:%S"),
                    )
                    state["window_locked"] = False  # reset trade lock for new window

                # Since Polymarket Gamma API might take 10-60+ seconds to accurately resolve 
                # the exact Chainlink strike price for the start of the window, we actively 
                # binary-search the Chainlink Oracle historically for the exact start_date.
                if window.price_to_beat == 0:
                    now = datetime.now(timezone.utc)
                    if now >= window.start_date:
                        target_ts = int(window.start_date.timestamp())
                        loop = asyncio.get_event_loop()
                        oracle_price = await loop.run_in_executor(None, fetch_historical_chainlink_btc_sync, target_ts)
                        if oracle_price is not None and oracle_price > 0:
                            window.price_to_beat = oracle_price
                            log.info(
                                "Accurately fetched historical start-of-window Chainlink Oracle price %s for %s",
                                oracle_price, window.slug
                            )
                
                # Preserve priceToBeat from previous iteration (already found)
                if (window.price_to_beat == 0
                        and old is not None
                        and old.slug == window.slug
                        and old.price_to_beat > 0):
                    window.price_to_beat = old.price_to_beat

                state["window"] = window

                # Poll faster while waiting for priceToBeat to appear
                if window.price_to_beat == 0:
                    await asyncio.sleep(2)
                    continue
            else:
                if old is not None:
                    log.info("No active window — entering idle state")
                state["window"] = None

            await asyncio.sleep(config.MARKET_RETRY_INTERVAL)
