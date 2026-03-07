"""
Authentication — ClobClient setup for EOA wallets + token allowance approval.
"""

import logging
from py_clob_client.client import ClobClient
from src import config

log = logging.getLogger("polybot")


def create_client() -> ClobClient:
    """Initialize and authenticate a ClobClient for an EOA wallet."""
    log.info("Initializing ClobClient (EOA, chain=%d)", config.CHAIN_ID)

    client = ClobClient(
        config.CLOB_HOST,
        key=config.POLY_PRIVATE_KEY,
        chain_id=config.CHAIN_ID,
        signature_type=config.SIGNATURE_TYPE,  # 0 = EOA
        funder=config.POLY_FUNDER_ADDRESS,
    )

    # Derive or create L1 API credentials (required for balance/trading)
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(creds)
    
    # Critical: The py-clob-client requires these explicit fields initialized 
    # to pass the auth headers for restricted endpoints like `get_balance_allowance`
    client.creds = creds
    client.api_key = creds.api_key
    client.api_secret = creds.api_secret
    client.api_passphrase = creds.api_passphrase

    log.info("API credentials set — ready to trade")

    return client


def approve_allowances() -> None:
    """
    One-time token allowance setup for EOA wallets.
    Approves USDC and ConditionalTokens for all three exchange contracts.
    Must be run before the first trade.
    """
    from web3 import Web3

    log.info("Setting token allowances for EOA wallet...")

    w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    account = w3.eth.account.from_key(config.POLY_PRIVATE_KEY)

    # Minimal ERC-20 approve ABI
    erc20_abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "spender", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function",
        }
    ]

    max_uint256 = 2**256 - 1
    tokens = [config.USDC_ADDRESS, config.CONDITIONAL_TOKENS_ADDRESS]
    spenders = [
        config.EXCHANGE_ADDRESS,
        config.NEG_RISK_EXCHANGE_ADDRESS,
        config.NEG_RISK_ADAPTER_ADDRESS,
    ]

    for token_addr in tokens:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(token_addr), abi=erc20_abi
        )
        for spender_addr in spenders:
            spender = Web3.to_checksum_address(spender_addr)
            nonce = w3.eth.get_transaction_count(account.address)
            tx = contract.functions.approve(spender, max_uint256).build_transaction(
                {
                    "from": account.address,
                    "nonce": nonce,
                    "gas": 60_000,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": config.CHAIN_ID,
                }
            )
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            status = "✓" if receipt["status"] == 1 else "✗"
            log.info(
                "  %s approve(%s → %s) tx=%s",
                status,
                token_addr[:10],
                spender_addr[:10],
                tx_hash.hex(),
            )

    log.info("All allowances set successfully!")
