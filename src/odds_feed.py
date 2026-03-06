"""
Token odds feed — continuously polls UP/DOWN midpoint prices from CLOB API.
"""

import logging
import asyncio

import aiohttp
from src import config

log = logging.getLogger("polybot")

CLOB_MIDPOINT_URL = f"{config.CLOB_HOST}/midpoint"


async def _fetch_midpoint(session: aiohttp.ClientSession, token_id: str) -> float:
    """Fetch midpoint price for a single token from the CLOB API."""
    try:
        async with session.get(
            CLOB_MIDPOINT_URL,
            params={"token_id": token_id},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status != 200:
                return 0.0
            data = await resp.json()
            return float(data.get("mid", 0))
    except Exception as e:
        log.debug("Midpoint fetch failed for %s: %s", token_id[:16], e)
        return 0.0


async def odds_feed_loop(state: dict) -> None:
    """
    Continuous loop that keeps state["up_odds"] and state["down_odds"]
    updated with live midpoint prices from the CLOB orderbook.
    """
    async with aiohttp.ClientSession() as session:
        while True:
            window = state.get("window")
            if window and window.up_token_id and window.down_token_id:
                up, down = await asyncio.gather(
                    _fetch_midpoint(session, window.up_token_id),
                    _fetch_midpoint(session, window.down_token_id),
                )
                if up > 0:
                    state["up_odds"] = up
                if down > 0:
                    state["down_odds"] = down
            await asyncio.sleep(2)
