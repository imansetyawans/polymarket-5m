"""
Equity calculator — total equity = USDC liquid balance + unredeemed winning positions.
"""

import logging
from typing import List
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
from src import config

log = logging.getLogger("polybot")


def get_usdc_balance(client: ClobClient) -> float:
    """Fetch USDC liquid balance from the CLOB API."""
    try:
        params = BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=config.SIGNATURE_TYPE,
        )
        balance = client.get_balance_allowance(params)
        if isinstance(balance, dict):
            raw = float(balance.get("balance", 0))
            # USDC has 6 decimals — convert from atomic if needed
            return raw / 1e6 if raw > 1_000_000 else raw
        return float(balance) if balance else 0.0
    except Exception as e:
        log.error("Failed to fetch USDC balance: %s", e)
        return 0.0


def get_unredeemed_winning_value(positions: List[dict]) -> float:
    """
    Calculate the face value of all unredeemed winning positions.
    Each winning token is worth $1.00 face value.
    """
    total = 0.0
    for pos in positions:
        outcome = pos.get("outcome", "")
        resolved = pos.get("resolved", False)
        size = float(pos.get("size", 0) or pos.get("quantity", 0) or 0)

        if resolved and outcome.lower() in ("winning", "won", "true"):
            total += size

    return total


def get_total_equity(client: ClobClient, positions: List[dict]) -> dict:
    """
    Calculate total equity:
      total = USDC liquid balance + face value of unredeemed winning positions.
    """
    usdc = get_usdc_balance(client)
    winning = get_unredeemed_winning_value(positions)
    total = usdc + winning

    return {
        "usdc_balance": usdc,
        "winning_value": winning,
        "total": total,
    }
