"""
Live BTC price feed — reads from Binance real-time public API.
Replaces the delayed Polygon Chainlink oracle for millisecond accuracy
for the 5m options strategy.
"""

import logging
import asyncio
import aiohttp
from typing import Optional
from src import config

log = logging.getLogger("polybot")

BINANCE_BTC_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"

async def price_feed_loop(state: dict) -> None:
    """
    Continuous loop that keeps state["btc_price"] updated with the latest
    real-time BTC/USDT price from Binance.
    """
    log.info("Starting real-time Binance BTC/USDT price feed...")

    timeout = aiohttp.ClientTimeout(total=3)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Initial fetch with visible logging
        try:
            async with session.get(BINANCE_BTC_URL) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data["price"])
                    state["btc_price"] = price
                    log.info("Initial BTC price (Binance): $%.2f", price)
                else:
                    log.warning("Initial Binance fetch failed (Status %d)", response.status)
        except Exception as e:
            log.warning("Initial Binance feed error: %s", e)

        # Continuous polling at exact configured interval
        while True:
            await asyncio.sleep(config.PRICE_FEED_INTERVAL)
            try:
                async with session.get(BINANCE_BTC_URL) as response:
                    if response.status == 200:
                        data = await response.json()
                        state["btc_price"] = float(data["price"])
            except Exception as e:
                log.debug("Binance price feed error: %s", e)
