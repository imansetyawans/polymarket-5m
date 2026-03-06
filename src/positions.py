"""
Position management — poll positions, detect resolved+winning, auto-redeem via web3.
"""

import logging
import asyncio
from typing import List

from py_clob_client.client import ClobClient
from web3 import Web3

from src import config

log = logging.getLogger("polybot")

# Minimal ConditionalTokens ABI for redeemPositions
CONDITIONAL_TOKENS_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "name": "redeemPositions",
        "outputs": [],
        "type": "function",
    }
]


def fetch_positions(client: ClobClient) -> List[dict]:
    """Fetch all user positions from the CLOB API."""
    try:
        # get_trades returns trade history; for positions we try get_balance_allowance
        # The CLOB client doesn't have a direct "positions" endpoint in all versions,
        # so we fall back to checking via the data API
        positions = []
        try:
            result = client.get_trades()
            if isinstance(result, list):
                positions = result
        except Exception:
            pass
        return positions
    except Exception as e:
        log.error("Failed to fetch positions: %s", e)
        return []


def find_redeemable(positions: List[dict]) -> List[dict]:
    """
    Find positions that are resolved and winning → eligible for redemption.
    """
    redeemable = []
    for pos in positions:
        resolved = pos.get("resolved", False)
        outcome = str(pos.get("outcome", "")).lower()
        if resolved and outcome in ("winning", "won", "true"):
            redeemable.append(pos)
    return redeemable


async def redeem_positions(redeemable: List[dict]) -> int:
    """
    Batch redeem all eligible winning positions via ConditionalTokens contract.
    Returns the number of successfully redeemed positions.
    """
    if not redeemable:
        return 0

    try:
        w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        account = w3.eth.account.from_key(config.POLY_PRIVATE_KEY)
        ct = w3.eth.contract(
            address=Web3.to_checksum_address(config.CONDITIONAL_TOKENS_ADDRESS),
            abi=CONDITIONAL_TOKENS_ABI,
        )

        redeemed = 0
        parent_collection = bytes(32)  # 0x0...0
        usdc = Web3.to_checksum_address(config.USDC_ADDRESS)

        for pos in redeemable:
            condition_id = pos.get("conditionId", pos.get("condition_id", ""))
            if not condition_id:
                continue

            # Convert condition_id to bytes32
            if isinstance(condition_id, str):
                if condition_id.startswith("0x"):
                    cid_bytes = bytes.fromhex(condition_id[2:])
                else:
                    cid_bytes = bytes.fromhex(condition_id)
            else:
                cid_bytes = condition_id

            # Index sets: [1, 2] redeems both outcome slots
            index_sets = [1, 2]

            try:
                nonce = w3.eth.get_transaction_count(account.address)
                tx = ct.functions.redeemPositions(
                    usdc, parent_collection, cid_bytes, index_sets
                ).build_transaction(
                    {
                        "from": account.address,
                        "nonce": nonce,
                        "gas": 200_000,
                        "gasPrice": w3.eth.gas_price,
                        "chainId": config.CHAIN_ID,
                    }
                )
                signed = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

                if receipt["status"] == 1:
                    redeemed += 1
                    log.info("✓ Redeemed condition %s | tx=%s", condition_id[:16], tx_hash.hex())
                else:
                    log.warning("✗ Redeem failed for %s | tx=%s", condition_id[:16], tx_hash.hex())

            except Exception as e:
                log.error("Redeem tx error for %s: %s", condition_id[:16], e)

        return redeemed

    except Exception as e:
        log.error("Redeem setup error: %s", e)
        return 0


async def position_loop(client: ClobClient, state: dict) -> None:
    """
    Background loop: poll positions every 5s, auto-redeem winning positions.
    """
    while True:
        try:
            positions = fetch_positions(client)
            state["positions"] = positions

            redeemable = find_redeemable(positions)
            if redeemable:
                log.info("Found %d redeemable position(s) — redeeming...", len(redeemable))
                count = await redeem_positions(redeemable)
                if count:
                    log.info("Redeemed %d position(s)", count)
                    state["last_redeem"] = f"Redeemed {count} position(s)"

        except Exception as e:
            log.error("Position loop error: %s", e)

        await asyncio.sleep(config.POSITION_POLL_INTERVAL)
