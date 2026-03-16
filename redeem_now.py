#!/usr/bin/env python3
"""Manual redemption script"""
import asyncio
from py_clob_client.client import ClobClient
from src.positions import get_w3, fetch_positions, find_redeemable, redeem_positions
from src.auth import create_client

async def main():
    client = create_client()
    w3 = get_w3()

    if not w3:
        print("❌ Failed to connect to RPC")
        return

    print("✓ Connected to RPC")
    print("Fetching positions...")

    trades = fetch_positions(client)
    print(f"Found {len(trades)} trades")

    positions = find_redeemable(client, w3, trades)
    print(f"Found {len(positions)} redeemable positions")

    if positions:
        count = await redeem_positions(w3, positions)
        print(f"✓ Redeemed {count} positions")
    else:
        print("No positions to redeem")

if __name__ == "__main__":
    asyncio.run(main())
