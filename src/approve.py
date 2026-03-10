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
    usdc_address = w3.to_checksum_address(config.USDC_ADDRESS)
    
    # List of spenders to approve
    spenders = [
        ("Standard Exchange", config.EXCHANGE_ADDRESS),
        ("Neg Risk Exchange", config.NEG_RISK_EXCHANGE_ADDRESS),
        ("Neg Risk Adapter", config.NEG_RISK_ADAPTER_ADDRESS),
    ]

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
            "outputs": [{"name": "", "type": "uint256"}], 
            "payable": False, 
            "stateMutability": "nonpayable", 
            "type": "function"
        }
    ]

    usdc = w3.eth.contract(address=usdc_address, abi=abi)
    max_amount = 2**256 - 1
    
    for name, addr in spenders:
        spender_address = w3.to_checksum_address(addr)
        log.info("--- Checking %s: %s ---", name, spender_address)
        
        try:
            current_allowance = usdc.functions.allowance(acct.address, spender_address).call()
            if current_allowance >= (max_amount / 2):
                log.info("  %s already has sufficient allowance.", name)
                continue
                
            log.info("  Building approval for %s...", name)
            tx = usdc.functions.approve(spender_address, max_amount).build_transaction({
                "from": acct.address,
                "nonce": w3.eth.get_transaction_count(acct.address),
                "gas": 100000,
                "gasPrice": w3.eth.gas_price
            })

            signed = w3.eth.account.sign_transaction(tx, priv)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            log.info("  Sent! Tx Hash: %s", tx_hash.hex())
            
            # Wait for receipt to avoid nonce collisions
            w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            log.info("  %s Approved!", name)
            
        except Exception as e:
            log.error("  Error approving %s: %s", name, e)

    log.info("--- All approvals completed! ---")


if __name__ == "__main__":
    approve_usdc()
