# Polymarket Auto-Trade Bot — Final Prompt Specification

> Build a Polymarket auto-trade bot with the following specifications.
> Read and follow the official Polymarket documentation before implementation.

---

## TECH STACK & UI

- Language: Python
- TUI Rich fancy terminal dashboard (real-time updating, refresh every 500ms)
- Dashboard displays:
  - Current time (WIB / UTC+7, millisecond precision)
  - Active market window & countdown to close
  - Current BTC price (live)
  - UP odds / DOWN odds (live)
  - Price to beat for active window
  - Gap between current BTC price vs price to beat
  - Last trade log
  - Open positions & status
  - Total equity (USDC liquid balance + face value of unredeemed winning positions)

---

## AUTHENTICATION

- Wallet type: EOA (MetaMask) → SIGNATURE_TYPE = 0
- CHAIN_ID = 137 (Polygon Mainnet)
- Read Polymarket documentation to implement the correct API key derivation and request signing flow for EOA wallets
- Config via `.env`:

```env
POLY_PRIVATE_KEY=
POLY_FUNDER_ADDRESS=
```

---

## TARGET MARKET

- Market: BTC `btc-updown-5m`
- Auto-detect the active market window via Polymarket API by matching current UTC time to the nearest upcoming `endDate`
- Each window duration: 5 minutes (300 seconds)
- Market is expected to run 24/7. If no active market is found, enter idle state — keep dashboard running and retry every 5 seconds

---

## PRICE TO BEAT

- **Definition:** the BTC reference price set by Polymarket that determines whether the market resolves UP or DOWN
- Fetch from Polymarket API when active window is detected
- Logic:
  - If BTC price at close > price to beat → **UP wins**
  - If BTC price at close < price to beat → **DOWN wins**
- Display on dashboard alongside the gap from current BTC price

---

## ENTRY STRATEGY — PRIMARY (T-5 seconds)

- At exactly **T-5.000 seconds** before market close (millisecond precision using `time.perf_counter` + `asyncio`):
  - Fetch current UP and DOWN odds
  - BUY the token with the **HIGHEST price** (closest to 1.00)
  - Order type: **FOK (Fill or Kill)**
  - Set slippage to the maximum value allowed by the CLOB API to ensure the order is successfully executed
- Per-window lock: maximum **1 trade per market window**

---

## ENTRY STRATEGY — SECONDARY (T-60 seconds, gap trigger)

- During the final **60 seconds** before close, continuously monitor:
  - `gap = abs(current_BTC_price - price_to_beat)`
  - If `gap > $120` AND no trade has been placed in this window:
    - Immediately BUY the token with the **HIGHEST price** (FOK)
    - Set slippage to the maximum value allowed by the CLOB API
    - Set per-window lock after order is sent
- If secondary trigger fires, the primary T-5 trigger will **NOT execute** (window is already locked)

---

## ORDER AMOUNT

- Configurable via `.env`:

```env
TRADE_AMOUNT_MODE=percent   # "percent" or "fixed"
TRADE_AMOUNT_VALUE=50       # 50 for 50%, or 10 for $10 USDC
```

- If `MODE = "percent"`:
  - `total_equity = USDC liquid balance + face value of all unredeemed winning positions`
  - `trade_size = (TRADE_AMOUNT_VALUE / 100) × total_equity`
  - Example: 50% of $100 total equity → trade_size = $50

- If `MODE = "fixed"`:
  - `trade_size = TRADE_AMOUNT_VALUE USDC`

- **Fallback:** if USDC liquid balance is below Polymarket's minimum order size, skip the trade and log a warning on the dashboard

---

## AUTO REDEEM

- Poll positions endpoint every **5 seconds** (background async loop)
- If any position has status = `resolved` + `winning`:
  - Batch redeem all eligible positions in one call
  - Log redeem result on dashboard
- Redeem loop runs in parallel and must **not interfere** with trade timing precision

---

## TIMEZONE

- All internal logic uses **UTC**
- All dashboard display uses **WIB (UTC+7)**
- Example: market close at UTC 04:40 → displayed as 11:40 WIB

---

## ERROR HANDLING

- If FOK order is rejected: log the reason, do **NOT** retry, skip window
- If any API call fails: retry up to **3x** with exponential backoff (0.5s → 1s → 2s)
- All errors and trade activity logged to: `bot.log`

---

## FULL CONFIG FILE (.env)

```env
POLY_PRIVATE_KEY=
POLY_FUNDER_ADDRESS=
TRADE_AMOUNT_MODE=percent
TRADE_AMOUNT_VALUE=50
GAP_TRIGGER_USD=120
ENTRY_SECONDS_BEFORE_CLOSE=5
GAP_TRIGGER_SECONDS_BEFORE_CLOSE=60
```
