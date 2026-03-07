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
- 🛡️ **Proxy Wallet System** — Gas-less relayer trading instantly directly from deposited USDC
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
# Required for live trading only (not needed for --sim or --dry-run)
POLY_PRIVATE_KEY=your_private_key_here
POLY_FUNDER_ADDRESS=your_wallet_address_here

# Proxy Wallet vs. EOA
SIGNATURE_TYPE=2                # 2 = Proxy Smart Wallet (No Gas Fees), 0 = EOA (Requires MATIC)

# Quantitative Strategy
TRADE_AMOUNT_MODE=percent       # "percent" or "fixed"
TRADE_AMOUNT_VALUE=50           # Scales Kelly fraction (e.g., 50% = Half-Kelly betting)
```

### 3. Run

```bash
# 🎮 Simulation (recommended to start) — $10 virtual balance
python -m src.main --sim

# 🎮 Simulation with custom balance
python -m src.main --sim 50

# 👀 Dry run — dashboard only, no trades
python -m src.main --dry-run

# 🚀 Live trading
python -m src.main

# 🔑 First-time setup — approve USDC token allowance
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

## Project Structure

```
poly-tui/
├── src/
│   ├── main.py          # Entry point & async orchestrator
│   ├── config.py        # Environment config loader
│   ├── auth.py          # Polymarket client & Proxy Wallet authentication
│   ├── market.py        # Market window discovery (Gamma API)
│   ├── price_feed.py    # Sub-second BTC precise ticker feed (Binance API)
│   ├── strategy.py      # Edge, Expected Value, Kelly Criterion computations
│   ├── trader.py        # FAK live CLOB order execution logic
│   ├── sim_trader.py    # Simulation trader with virtual portfolio
│   ├── positions.py     # Position tracking & redemption
│   ├── equity.py        # USDC balance & equity calculation
│   ├── dashboard.py     # Rich TUI dashboard renderer
│   └── logger.py        # Logging setup with in-memory buffer
├── .env.example         # Environment template
├── requirements.txt     # Python dependencies
└── README.md
```

---

## Requirements

- Python 3.10+
- Polygon wallet with USDC (for live trading only)
- Internet connection (for Polymarket APIs and Chainlink oracle)

### Key Dependencies

| Package | Purpose |
|---------|---------|
| `py-clob-client` | Polymarket CLOB API client |
| `web3` | Chainlink oracle reads on Polygon |
| `rich` | Terminal UI dashboard |
| `aiohttp` | Async HTTP for Gamma API |
| `python-dotenv` | Environment configuration |

---

## API Endpoints Used

| API | Endpoint | Purpose |
|-----|----------|---------|
| Gamma | `GET /events?slug=...` | Market window discovery |
| CLOB | `GET /midpoint?token_id=...` | UP/DOWN token odds |
| CLOB | `POST /order` | Trade execution (live only) |
| Chainlink | Polygon contract call | BTC/USD price oracle |

---

## License

MIT
