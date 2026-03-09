# ⚡ Polymarket BTC Auto-Trader

A terminal-based (TUI) auto-trading bot for [Polymarket](https://polymarket.com) **Bitcoin Up or Down — 5 Minutes** markets.

Built with Python, Rich, and the Polymarket CLOB API.

![Dashboard Preview](https://img.shields.io/badge/status-active-brightgreen) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

---

## Features

- 🎯 **Continuous Auto-Trading** — BTC Up/Down 5-minute windows on Polymarket
- 🧠 **Kelly Criterion Strategy** — Trades strictly on mathematical Edge and +EV variables
- 📊 **Real-time TUI dashboard** — Countdown, orderbook streaming, edge calculation, live PnL 
- ₿ **Binance Live Ticker** — Sub-second exact BTC price sync (zero on-chain lag)
- 🎮 **Simulation Mode** — Paper trade with virtual balance and live data
- 🛡️ **EOA & Proxy Support** — Trade directly from your wallet or via Polymarket Proxy
- 🔄 **Auto-Redeem Winnings** — Automatically claims winning positions back to USDC
- ⚡ **Private RPC Support** — Prioritizes Alchemy/Custom RPCs for high-speed execution
- 🚀 **FAK Execution** — Dynamic Fill-and-Kill market orders to safely snipe shallow liquidity

## Quick Start

### 1. Clone & Install

```bash
git clone <repo-url> poly-tui
cd poly-tui
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Required for live trading only
POLY_PRIVATE_KEY=your_private_key_here
POLY_FUNDER_ADDRESS=your_direct_wallet_address

# Signature Type
SIGNATURE_TYPE=0                # 0 = EOA (Direct), 2 = Polymarket Proxy

# Private RPC (Recommended for speed)
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/your-key

# Quantitative Strategy
EDGE_THRESHOLD=0.07             # 7% edge minimum
KELLY_FRACTION=0.5              # Half-Kelly betting
```

### 3. Run

```bash
# 🎮 Simulation (recommended to start) — $10 virtual balance
python -m src.main --sim

# 👀 Dry run — dashboard only, no trades
python -m src.main --dry-run

# 🚀 Live trading
python -m src.main

# 🔑 First-time EOA setup — approve USDC token allowance
python -m src.main --approve
```

Press `Ctrl+C` to stop.

---

## Dashboard

```
╭──────────────────────────────────────────────────────────────────────────╮
│    ⚡ POLYMARKET AUTO-TRADER  │  🟢 ACTIVE  │  🕐 13:23:46 WIB         │
╰──────────────────────────────────────────────────────────────────────────╯
╭───────── 📊 Market Window ─────────╮╭──────────── 💰 Equity ─────────────╮
│  Window        btc-updown-5m-1...  ││  USDC Balance      $12.48          │
│  Closes (WIB)  13:25:00            ││  Unredeemed Wins   $0.00           │
│  Countdown     01:13.857           ││  Total Equity      $12.48          │
│  Price to Beat $67,954.01          │╰────────────────────────────────────╯
╰────────────────────────────────────╯
╭────── ₿ BTC Price (Binance) ───────╮╭── 📋 Positions | Live PnL: +$1.24 ─╮
│  BTC Price     $67,895.65          ││  Market         Side   Size Status │
│  Gap           ▼ $58.36            ││  0xf6eadf9e...  BUY UP $8.50 CONF  │
╰────────────────────────────────────╯╰────────────────────────────────────╯
╭────────── 📈 Quant Strategy ───────╮╭──────────── 📝 Trade Log ──────────╮
│  UP / DOWN Odds   0.3450 / 0.6550  ││ Last Trade: BUY DOWN $1.34         │
│  Est. p_true      0.3821           ││                                    │
│  Edge             +23.71%          ││ [13:23:36.479] Starting Live Trade │
│  Expected Value   +1.6349          ││ [13:24:00.123] FAK BUY DOWN filled │
│  Target Side      ⬇ DOWN           │╰────────────────────────────────────╯
╰────────────────────────────────────╯
```

---

## How It Works

### Market Discovery
The bot continuously scans for active `btc-updown-5m-{timestamp}` windows on Polymarket's Gamma API. Each window represents a 5-minute prediction market on whether BTC will go up or down.

### Price Data
- **BTC Price**: Read accurately from the **Live Binance Ticker** via REST. On-chain oracles were completely removed due to lag issues; the bot now utilizes sub-second precise live market feeds to prevent front-running.
- **Price to Beat**: Locked exactly at window generation (via Gamma API metadata or captured locally).

### Quantitative Engine (Continuous Evaluation)
The bot previously relied on time constraints (waiting strictly until T-5s). **This has been completely rewritten.** The bot now streams orderbook odds 24/7 and runs them against a rigorous mathematical standard curve model mapping the BTC price gap/volatility against time remaining. 
If the calculated Edge against the top-of-book market implies a positive Expected Value (EV > 0), the bot **instantly trades unconditionally of the time remaining on the clock**.
- Uses internal **Kelly Criterion** math multiplied by `TRADE_AMOUNT_VALUE` to accurately dictate bet size relative to the safety of the perceived mathematical edge. Minimum order dynamically floored at `$1.00`.

### Fill-And-Kill (FAK) Order Mechanics
Orders execute against the live Polymarket Central Limit Order Book (CLOB). To protect Kelly Bets from getting entirely rejected by shallow orderbooks, execution utilizes `OrderType.FAK`. This instantly scoops all available liquidity mathematically viable without halting or crashing if the exact size isn't immediately attainable.

### Proxy Smart Wallet Trading
The bot has been deeply updated to support `SIGNATURE_TYPE=2`. This seamlessly passes trades through Polymarket's relayer network natively utilizing deposited USDC funds without enforcing manually injected MATIC gas fees.

---

## Technical Architecture

### Live Price & Market Data
- **High-Speed Execution**: The bot prioritizes `POLYGON_RPC_URL` from your `.env` for all on-chain operations (approvals, redemptions). It includes an automatic **RPC Rotation** fallback to ensure 100% uptime.
- **Binance Feed**: Real-time BTC price is pulled from Binance REST/WebSocket to ensure zero-lag compared to on-chain oracles.
- **Gamma API**: Used for discovering active market windows and resolving results.

### Auto-Redeem System
The bot features a background redemption engine (`src/positions.py`):
1. Monitors open positions for "Resolved" status.
2. Identifies winning outcomes.
3. Automatically executes `redeemPositions` on the Polymarket contract using your private RPC.
4. Corrects for sequential nonces to ensure multiple wins are claimed instantly.

### EOA vs Proxy Mode
- **EOA (`SIGNATURE_TYPE=0`)**: Trades directly from your main wallet. Faster execution but requires MATIC for gas and a one-time `--approve` call.
- **Proxy (`SIGNATURE_TYPE=2`)**: Uses Polymarket's smart wallet. Gas-less trading handled by Polymarket relayers, but may have slight relayer latency.

---

## Project Structure

```
poly-tui/
├── src/
│   ├── main.py          # Entry point & async orchestrator
│   ├── config.py        # Environment config loader (supports private RPC)
│   ├── auth.py          # EOA/Proxy Auth & Multi-RPC approval logic
│   ├── market.py        # Market window discovery & RPC fallback
│   ├── price_feed.py    # Sub-second BTC precise ticker feed
│   ├── strategy.py      # Quantum Edge & Kelly Criterion math
│   ├── trader.py        # FAK market order execution
│   ├── sim_trader.py    # Simulation trader with virtual portfolio
│   ├── positions.py     # Background Auto-Redeem engine
│   ├── equity.py        # USDC & Equity tracking
│   ├── dashboard.py     # Rich TUI dashboard
│   └── logger.py        # Logging with in-memory buffer
├── .env.example         # Updated environment template
├── requirements.txt     # Python dependencies
└── README.md
```

---

## Requirements

- Python 3.10+
- Polygon wallet with **USDC.e** (Bridged USDC)
- **MATIC** (if using EOA mode)
- [Alchemy](https://www.alchemy.com/) or [Infura](https://www.infura.io/) RPC (Optional but highly recommended)

### Key Dependencies

| Package | Purpose |
|---------|---------|
| `py-clob-client` | Polymarket CLOB API client |
| `web3` | On-chain interactions (Approvals/Redeem) |
| `rich` | Terminal UI dashboard |
| `aiohttp` | Async HTTP for APIs |

---

## API Endpoints Used

| API | Endpoint | Purpose |
|-----|----------|---------|
| Gamma | `GET /events?slug=...` | Market window discovery |
| CLOB | `GET /midpoint?token_id=...` | UP/DOWN token odds |
| CLOB | `POST /order` | Trade execution (live only) |

---

## License

MIT
