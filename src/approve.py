"""
Script to approve USDC allowance for the Polymarket Exchange contract.
Run this once whenever you change the wallet (POLY_PRIVATE_KEY) in your .env file.
"""

import os
import sys
import time
import logging

import dotenv
from web3 import Web3

# Ensure we can import from src
sys.path.append(os.getcwd())
dotenv.load_dotenv()

from src import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
log = logging.getLogger("polybot.approve")


def approve_usdc():
    priv = config.POLY_PRIVATE_KEY
    if not priv:
        log.error("POLY_PRIVATE_KEY not found in .env!")
        return

    # Initialize Web3
    rpc_url = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com/")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        log.error("Failed to connect to Polygon RPC: %s", rpc_url)
        return

    # Load Account
    acct = w3.eth.account.from_key(priv)
    log.info("Wallet Address: %s", acct.address)

    # Contract Addresses
    usdc_address = w3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")  # USDC.e on Polygon
    exchange_address = w3.to_checksum_address(config.EXCHANGE_ADDRESS)

    log.info("Checking current allowance for Polymarket Exchange: %s", exchange_address)

    # Minimal ERC20 ABI for allowance & approve
    abi = [
        {
            "constant": True,
            "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
            "name": "allowance",
            "outputs": [{"name": "", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": False, 
            "inputs": [{"name": "spender", "type": "address"}, {"name": "value", "type": "uint256"}], 
            "name": "approve", 
            "outputs": [{"name": "", "type": "bool"}], 
            "payable": False, 
            "stateMutability": "nonpayable", 
            "type": "function"
        }
    ]

    usdc = w3.eth.contract(address=usdc_address, abi=abi)
    
    # Check existing allowance
    current_allowance = usdc.functions.allowance(acct.address, exchange_address).call()
    
    # We want max allowance
    max_amount = 2**256 - 1
    
    if current_allowance >= (max_amount / 2):
        log.info("Wallet already has sufficient allowance approved! No action needed.")
        return
        
    log.info("Allowance is insufficient. Building approval transaction...")

    # Build Transaction
    tx = usdc.functions.approve(exchange_address, max_amount).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 100000,
        "gasPrice": w3.eth.gas_price
    })

    log.info("Signing transaction...")
    signed = w3.eth.account.sign_transaction(tx, priv)
    
    log.info("Broadcasting transaction...")
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    
    log.info("Sent! Transaction Hash: %s", tx_hash.hex())
    log.info("Waiting for network confirmation (this may take 10-30 seconds)...")

    # Wait for receipt
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status == 1:
            log.info("SUCCESS! Transaction confirmed in block %d.", receipt.blockNumber)
            log.info("Your wallet is now fully approved for the Polymarket bot.")
        else:
            log.error("Transaction FAILED! Status: %d. Check block explorer.", receipt.status)
    except Exception as e:
        log.error("Error waiting for transaction receipt: %s", e)


if __name__ == "__main__":
    approve_usdc()
