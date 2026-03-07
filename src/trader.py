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





async def _execute_market_order(
    client: ClobClient,
    token_id: str,
    token_label: str,
    trade_size: float,
    state: dict,
) -> bool:
    """
    Execute a Fill-and-Kill (FAK) market order.
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
            "Placing FAK BUY %s | size=$%.2f | token=%s...",
            token_label, trade_size, token_id[:16],
        )

        # Create market order — amount is in USDC
        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=trade_size,
            side=BUY,
            order_type=OrderType.FAK
        )

        signed = client.create_market_order(order_args)
        resp = client.post_order(signed, orderType=OrderType.FAK)

        # Parse response
        if isinstance(resp, dict):
            status = resp.get("status", resp.get("orderStatus", "UNKNOWN"))
            order_id = resp.get("orderID", resp.get("id", ""))
        else:
            status = str(resp)
            order_id = ""

        log.info(
            "FAK order result: status=%s | order=%s",
            status, order_id[:16] if order_id else "N/A",
        )

        if "reject" in str(status).lower() or "fail" in str(status).lower():
            reason = resp.get("message", "") if isinstance(resp, dict) else str(resp)
            log.warning("FAK REJECTED: %s — skipping window (no retry)", reason)
            state["last_trade"] = f"REJECTED — {reason}"
        else:
            state["last_trade"] = f"BUY {token_label} ${trade_size:.2f} | {status}"

        return True

    except Exception as e:
        log.error("FAK order failed: %s — skipping window", e)
        state["last_trade"] = f"ERROR — {e}"
        return False


async def _execute_sell_order(
    client: ClobClient,
    token_id: str,
    token_label: str,
    num_shares: float,
    state: dict,
) -> bool:
    """
    Execute a FAK market SELL order to immediately dump owned tokens.
    Returns True if order was placed, False on error.
    """
    from py_clob_client.order_builder.constants import SELL
    from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
    try:
        # 1. Fetch exact token balance to avoid Builder orderbook failure
        exact_shares = num_shares
        try:
            resp = client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
            )
            # Response is typically a list or dict
            if isinstance(resp, list) and len(resp) > 0:
                exact_shares = float(resp[0].get("balance", "0"))
            elif isinstance(resp, dict):
                exact_shares = float(resp.get("balance", "0"))
        except Exception as e:
            log.warning("Could not fetch exact token balance: %s. Using estimate.", e)

        if exact_shares <= 0:
            log.warning("Pre-Close Auto-Sell aborted: We do not own any shares of %s", token_id[:16])
            state["last_redeem"] = "Pre-Close FAK Blocked: Zero Balance"
            return False

        log.info(
            "Placing FAK SELL %s | exact_shares=%.2f | token=%s...",
            token_label, exact_shares, token_id[:16],
        )

        # Create market SELL order — amount is in Shares
        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=exact_shares,
            side=SELL,
            order_type=OrderType.FAK
        )

        signed = client.create_market_order(order_args)
        resp = client.post_order(signed, orderType=OrderType.FAK)

        if isinstance(resp, dict):
            status = resp.get("status", resp.get("orderStatus", "UNKNOWN"))
            order_id = resp.get("orderID", resp.get("id", ""))
        else:
            status = str(resp)
            order_id = ""

        log.info(
            "SELL order result: status=%s | order=%s",
            status, order_id[:16] if order_id else "N/A",
        )

        if "reject" in str(status).lower() or "fail" in str(status).lower():
            reason = resp.get("message", "") if isinstance(resp, dict) else str(resp)
            log.warning("SELL REJECTED: %s", reason)
            state["last_trade"] = f"SELL REJECTED — {reason}"
            return False
            
        return True

    except Exception as e:
        log.error("SELL order failed: %s", e)
        return False


async def trade_loop(client: ClobClient, state: dict) -> None:
    """
    Main trade execution loop using quantitative Edge-EV-Kelly strategy.
      - Wait for active market window
      - Apply strategy at gap trigger and primary entry timings
      - Lock window after any trade
    """
    from src.strategy import evaluate_market
    from src.equity import get_total_equity

    while True:
        window = state.get("window")
        if not window:
            await asyncio.sleep(0.5)
            continue

        now = datetime.now(timezone.utc)
        seconds_to_close = (window.end_date - now).total_seconds()
        state["seconds_to_close"] = seconds_to_close

        # Check if we should execute a pre-close sell (0.5s before resolution)
        if state.get("window_locked", False):
            if not state.get("sell_locked", False) and state.get("position_shares", 0) > 0:
                if 0.0 < seconds_to_close <= 0.5:
                    log.info("PRE-CLOSE AUTO-SELL TRIGGERED: selling %.2f shares", state["position_shares"])
                    sell_token = state["position_token_id"]
                    sell_label = state.get("signal_side", "UNKNOWN")
                    
                    sell_success = await _execute_sell_order(
                        client, 
                        sell_token, 
                        sell_label, 
                        state["position_shares"], 
                        state
                    )
                    
                    state["sell_locked"] = True
                    if sell_success:
                        log.info("Pre-close auto-sell fired successfully.")
                        state["last_redeem"] = "Pre-Close FAK Auto-Sold"
                    else:
                        log.error("Pre-close auto-sell failed.")

            # Continue high-frequency ticking if window is locked to wait for sell
            await asyncio.sleep(0.05)
            continue

        btc_price = state.get("btc_price", 0)
        up_odds = state.get("up_odds", 0)
        down_odds = state.get("down_odds", 0)
        positions = state.get("positions", [])

        # Avoid evaluating before prices and odds are populated
        if btc_price <= 0 or window.price_to_beat <= 0 or up_odds <= 0 or down_odds <= 0:
            await asyncio.sleep(0.5)
            continue

        # Get balance for Kelly sizing
        equity = get_total_equity(client, positions)
        total_balance = equity["total"]

        # Run quantitative model
        signal = evaluate_market(
            btc_price=btc_price,
            price_to_beat=window.price_to_beat,
            seconds_remaining=seconds_to_close,
            up_odds=up_odds,
            down_odds=down_odds,
            balance=total_balance,
            sigma_per_sec=config.BTC_VOLATILITY_PER_SEC,
            edge_threshold=config.EDGE_THRESHOLD,
            kelly_fraction=config.KELLY_FRACTION,
            entry_seconds=config.ENTRY_SECONDS_BEFORE_CLOSE,
            gap_trigger_percent=config.GAP_TRIGGER_PERCENT
        )
        
        # If window changed, reset state
        state_window = state.get("window")
        if not state_window or state_window.slug != window.slug:
            log.info("--- New 5min Window Detected: %s ---", window.slug)
            state["window"] = window
            state["window_locked"] = False
            state["last_trade"] = "No trades yet"
            state["position_shares"] = 0
            state["sell_locked"] = False
            state["up_odds"] = 0
            state["down_odds"] = 0
            # Reset analytics
            for k in ["p_true", "edge", "ev", "kelly_size", "signal_side", "signal_reason"]:
                state.pop(k, None)

        if signal:
            # Update state for dashboard
            state["p_true"] = signal.p_true
            state["edge"] = signal.edge
            state["ev"] = signal.ev
            state["kelly_size"] = signal.kelly_size
            state["signal_side"] = signal.side
            state["signal_reason"] = signal.reason

            if signal.should_trade:
                # ── LIVE TRADING: Fetch exact orderbook prices right before execution
                # The continuous loop uses the 1-second cached background odds.
                # Once the math says YES, we must verify with the live API to prevent slippage.
                prices = _get_token_prices(client, window.up_token_id, window.down_token_id)
                exact_up_odds = prices["up"]
                exact_down_odds = prices["down"]
                
                # Update state
                state["up_odds"] = exact_up_odds
                state["down_odds"] = exact_down_odds

                # Re-evaluate the math with the exact, lowest-latency prices
                exact_signal = evaluate_market(
                    btc_price=btc_price,
                    price_to_beat=window.price_to_beat,
                    seconds_remaining=seconds_to_close,
                    up_odds=exact_up_odds,
                    down_odds=exact_down_odds,
                    balance=total_balance,
                    sigma_per_sec=config.BTC_VOLATILITY_PER_SEC,
                    edge_threshold=config.EDGE_THRESHOLD,
                    kelly_fraction=config.KELLY_FRACTION,
                    entry_seconds=config.ENTRY_SECONDS_BEFORE_CLOSE,
                    gap_trigger_percent=config.GAP_TRIGGER_PERCENT
                )
                
                if not exact_signal.should_trade:
                    log.warning("Trade aborted: Exact live prices erased the mathematical edge.")
                    state["last_trade"] = "ABORTED — Edge lost on live price check"
                    await asyncio.sleep(0.5)
                    continue
                
                # Proceed with exact signal
                token_id = window.up_token_id if exact_signal.side == "UP" else window.down_token_id
                
                log.info(
                    "TRADE SIGNAL: BUY %s @ %.4f | Edge: %.2f%% | EV: %.3f | Kelly Size: $%.2f",
                    exact_signal.side, exact_signal.price, exact_signal.edge * 100, exact_signal.ev, exact_signal.kelly_size
                )
                
                success = await _execute_market_order(client, token_id, exact_signal.side, exact_signal.kelly_size, state)
                state["window_locked"] = True
                
                # To sell the tokens back, we need to know exactly how many we bought
                # We estimate shares by dividing Kelly size / execution price.  
                # For exact shares we would need to ping `client.get_balance()`, but estimate is often OK for FAK.
                # Since the exact bought size requires polling the blockchain, we fetch it via get_portfolio or just ask to sell 1000 shares FAK.
                # Actually, sending a massive FAK share size (e.g., 99999) safely tells the CLOB "Sell ALL my shares".
                if success:
                    state["position_token_id"] = token_id
                    state["position_shares"] = 999999.0  # FAK sell-all trick
                    
                log.info("Window locked — no further buys this window")
            else:
                log.info("SIGNAL SKIP: %s", signal.reason)
        else:
            log.warning("Not enough data for strategy eval — skipping")
            
        await asyncio.sleep(0.5)

        # Not yet in trade zone — sleep briefly
        await asyncio.sleep(0.1)
