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

    # Use private RPC if provided, otherwise rotate public ones
    rpcs = [config.POLYGON_RPC_URL] if config.POLYGON_RPC_URL else []
    rpcs += [
        "https://polygon-bor-rpc.publicnode.com",
        "https://polygon.llamarpc.com",
        "https://1rpc.io/matic",
        "https://rpc-mainnet.maticvigil.com"
    ]
    
    w3 = None
    for url in rpcs:
        try:
            temp_w3 = Web3(Web3.HTTPProvider(url))
            if temp_w3.is_connected():
                w3 = temp_w3
                log.info("Connected to Polygon via %s", url)
                break
        except:
            continue
            
    if not w3:
        log.error("Could not connect to any Polygon RPC for approvals.")
        return

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

    # Get starting nonce
    base_nonce = w3.eth.get_transaction_count(account.address)
    tx_index = 0

    for token_addr in tokens:
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(token_addr), abi=erc20_abi
        )
        for spender_addr in spenders:
            spender = Web3.to_checksum_address(spender_addr)
            tx = contract.functions.approve(spender, max_uint256).build_transaction(
                {
                    "from": account.address,
                    "nonce": base_nonce + tx_index,
                    "gas": 60_000,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": config.CHAIN_ID,
                }
            )
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            log.info("  Sent approve(%s → %s) tx=%s", token_addr[:10], spender_addr[:10], tx_hash.hex())
            
            # Wait for each receipt to ensure Polygon doesn't drop consecutive transactions
            try:
                w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            except Exception as e:
                log.warning("  Timeout or error waiting for receipt: %s", e)
                
            tx_index += 1

    log.info("All allowances set successfully!")
