"""
Trade execution — primary (T-5s) and secondary (gap trigger) entry strategies.
"""

import logging
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

from src import config
from src.equity import get_total_equity

log = logging.getLogger("polybot")

# Minimum order size on Polymarket (in USDC)
MIN_ORDER_SIZE = 1.0


def _get_token_prices(client: ClobClient, up_token: str, down_token: str) -> dict:
    """Fetch current UP and DOWN token prices from the CLOB."""
    try:
        up_price = client.get_price(up_token, side="BUY")
        down_price = client.get_price(down_token, side="BUY")

        # The API may return a dict with 'price' key or a raw float
        if isinstance(up_price, dict):
            up_price = float(up_price.get("price", 0))
        else:
            up_price = float(up_price or 0)

        if isinstance(down_price, dict):
            down_price = float(down_price.get("price", 0))
        else:
            down_price = float(down_price or 0)

        return {"up": up_price, "down": down_price}

    except Exception as e:
        log.error("Failed to fetch token prices: %s", e)
        return {"up": 0, "down": 0}


def _calculate_trade_size(client: ClobClient, positions: list) -> float:
    """Calculate trade size based on config mode (percent or fixed)."""
    if config.TRADE_AMOUNT_MODE == "fixed":
        return config.TRADE_AMOUNT_VALUE

    # Percent mode
    equity = get_total_equity(client, positions)
    total = equity["total"]
    size = (config.TRADE_AMOUNT_VALUE / 100.0) * total
    return round(size, 2)


async def _execute_fok_order(
    client: ClobClient,
    token_id: str,
    token_label: str,
    trade_size: float,
    state: dict,
) -> bool:
    """
    Execute a Fill-or-Kill market order.
    Returns True if order was placed (regardless of fill), False on error.
    """
    if trade_size < MIN_ORDER_SIZE:
        log.warning(
            "Trade size $%.2f below minimum $%.2f — skipping this window",
            trade_size, MIN_ORDER_SIZE,
        )
        state["last_trade"] = f"SKIPPED — size ${trade_size:.2f} below minimum"
        return False

    try:
        log.info(
            "Placing FOK BUY %s | size=$%.2f | token=%s...",
            token_label, trade_size, token_id[:16],
        )

        # Create FOK market order — amount is in USDC
        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=trade_size,
            side=BUY,
        )

        signed = client.create_market_order(order_args)
        resp = client.post_order(signed, order_type=OrderType.FOK)

        # Parse response
        if isinstance(resp, dict):
            status = resp.get("status", resp.get("orderStatus", "UNKNOWN"))
            order_id = resp.get("orderID", resp.get("id", ""))
        else:
            status = str(resp)
            order_id = ""

        log.info(
            "FOK order result: status=%s | order=%s",
            status, order_id[:16] if order_id else "N/A",
        )

        if "reject" in str(status).lower() or "fail" in str(status).lower():
            reason = resp.get("message", "") if isinstance(resp, dict) else str(resp)
            log.warning("FOK REJECTED: %s — skipping window (no retry)", reason)
            state["last_trade"] = f"REJECTED — {reason}"
        else:
            state["last_trade"] = f"BUY {token_label} ${trade_size:.2f} | {status}"

        return True

    except Exception as e:
        log.error("FOK order failed: %s — skipping window", e)
        state["last_trade"] = f"ERROR — {e}"
        return False


async def trade_loop(client: ClobClient, state: dict) -> None:
    """
    Main trade execution loop:
      1. Wait for an active market window
      2. During T-60s → T-5s: check gap trigger (secondary strategy)
      3. At T-5s: execute primary strategy
      4. Lock window after any trade
    """
    while True:
        window = state.get("window")
        if not window:
            await asyncio.sleep(0.5)
            continue

        # Already traded this window?
        if state.get("window_locked", False):
            await asyncio.sleep(0.5)
            continue

        now = datetime.now(timezone.utc)
        seconds_to_close = (window.end_date - now).total_seconds()

        # Update state for dashboard
        state["seconds_to_close"] = seconds_to_close

        # ── SECONDARY ENTRY: gap trigger (T-60s to T-5s) ────────
        if config.GAP_TRIGGER_SECONDS_BEFORE_CLOSE >= seconds_to_close > config.ENTRY_SECONDS_BEFORE_CLOSE:
            btc_price = state.get("btc_price", 0)
            if btc_price > 0 and window.price_to_beat > 0:
                gap = abs(btc_price - window.price_to_beat)
                state["gap"] = gap

                if gap > config.GAP_TRIGGER_USD:
                    log.info(
                        "GAP TRIGGER! gap=$%.2f > $%.2f threshold at T-%.1fs",
                        gap, config.GAP_TRIGGER_USD, seconds_to_close,
                    )

                    # Determine which token has the highest price (most likely winner)
                    prices = _get_token_prices(client, window.up_token_id, window.down_token_id)
                    state["up_odds"] = prices["up"]
                    state["down_odds"] = prices["down"]

                    if prices["up"] >= prices["down"]:
                        token_id = window.up_token_id
                        token_label = "UP"
                    else:
                        token_id = window.down_token_id
                        token_label = "DOWN"

                    trade_size = _calculate_trade_size(client, state.get("positions", []))
                    await _execute_fok_order(client, token_id, token_label, trade_size, state)

                    # Lock this window
                    state["window_locked"] = True
                    log.info("Window locked — no further trades this window")
                    continue

        # ── PRIMARY ENTRY: T-5s ──────────────────────────────────
        if 0 < seconds_to_close <= config.ENTRY_SECONDS_BEFORE_CLOSE + 0.1:
            # Precision wait until exactly T-5s
            target_time = window.end_date.timestamp() - config.ENTRY_SECONDS_BEFORE_CLOSE
            now_perf = time.time()

            if now_perf < target_time:
                # Use perf_counter for precision sleep
                wait = target_time - now_perf
                if wait > 0:
                    ref = time.perf_counter()
                    while (time.perf_counter() - ref) < wait:
                        await asyncio.sleep(0.001)  # 1ms granularity

            log.info("PRIMARY ENTRY at T-%.3fs", seconds_to_close)

            # Fetch prices
            prices = _get_token_prices(client, window.up_token_id, window.down_token_id)
            state["up_odds"] = prices["up"]
            state["down_odds"] = prices["down"]

            # Pick the token with the highest price (closest to 1.00)
            if prices["up"] >= prices["down"]:
                token_id = window.up_token_id
                token_label = "UP"
            else:
                token_id = window.down_token_id
                token_label = "DOWN"

            trade_size = _calculate_trade_size(client, state.get("positions", []))
            await _execute_fok_order(client, token_id, token_label, trade_size, state)

            # Lock this window
            state["window_locked"] = True
            log.info("Window locked — waiting for next window")
            continue

        # Window close passed — wait for next discovery cycle
        if seconds_to_close <= 0:
            await asyncio.sleep(1)
            continue

        # Not yet in trade zone — sleep briefly
        await asyncio.sleep(0.1)
