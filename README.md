# ⚡ Polymarket BTC Auto-Trader

A terminal-based (TUI) auto-trading bot for [Polymarket](https://polymarket.com) **Bitcoin Up or Down — 5 Minutes** markets.

Built with Python, Rich, and the Polymarket CLOB API.

![Dashboard Preview](https://img.shields.io/badge/status-active-brightgreen) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

---

## Features

- 🎯 **Auto-trades** BTC Up/Down 5-minute windows on Polymarket
- 📊 **Real-time TUI dashboard** with countdown, odds, BTC price, equity
- ₿ **Chainlink BTC/USD oracle** — same price source as Polymarket
- 🎮 **Simulation mode** — paper trade with virtual balance, no real money
- 🔄 **Auto window detection** — finds active 5-minute markets automatically
- 📈 **Dual entry strategies** — primary (T-5s) and gap trigger (T-60s)
- 💰 **P&L tracking** — win/loss record, balance, positions

---

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

# Trade Settings
TRADE_AMOUNT_MODE=percent       # "percent" or "fixed"
TRADE_AMOUNT_VALUE=50           # 50% of equity, or $50 fixed
GAP_TRIGGER_USD=120             # gap trigger threshold in USD
ENTRY_SECONDS_BEFORE_CLOSE=5    # primary entry at T-5s
GAP_TRIGGER_SECONDS_BEFORE_CLOSE=60  # secondary trigger window
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
╭──────────────────────────────────────────────────────────────╮
│  ⚡ POLYMARKET AUTO-TRADER  │  🎮 SIM  │  🕐 08:41:29 WIB   │
╰──────────────────────────────────────────────────────────────╯
╭──── 📊 Market Window ────╮╭──────── 💰 Equity ────────╮
│  Window     btc-updown…  ││  USDC Balance      $8.23  │
│  Closes     08:45:00     ││  Unredeemed Wins   $0.00  │
│  Countdown  03:30.275    ││  Total Equity      $8.23  │
│  Price Beat $70,910.11   │╰────────────────────────────╯
╰──────────────────────────╯
╭── ₿ BTC Price (Chainlink) ──╮╭─── 🎰 Token Odds ───╮
│  BTC Price    $70,895.65     ││  UP Odds    0.8500   │
│  Gap          ▼ $14.46       ││  DOWN Odds  0.1500   │
│  Gap Status   Normal         ││  Signal     ⬆ UP     │
╰──────────────────────────────╯╰──────────────────────╯
```

---

## How It Works

### Market Discovery
The bot continuously scans for active `btc-updown-5m-{timestamp}` windows on Polymarket's Gamma API. Each window represents a 5-minute prediction market on whether BTC will go up or down.

### Price Data
- **BTC Price**: Read directly from the **Chainlink BTC/USD oracle** on Polygon — the same data source Polymarket uses for resolution
- **Price to Beat**: Fetched from the previous window's `eventMetadata.priceToBeat` via Gamma API, matching exactly what Polymarket displays

### Entry Strategies

| Strategy | Timing | Condition |
|----------|--------|-----------|
| **Primary** | T-5s before close | Always triggers — buys the favored token |
| **Gap Trigger** | T-60s to T-5s | Fires when BTC gap > $120 from price-to-beat |

### Token Selection
The bot buys the token (UP or DOWN) with the higher midpoint price from the CLOB orderbook, as it represents the market's favored outcome.

### Simulation Mode
- Uses **real market data** — live windows, live Chainlink price, live CLOB odds
- Trades with a **virtual balance** (default $10)
- After each window closes, polls Gamma API to determine the actual outcome
- Tracks **W/L record, P&L, and running balance**

---

## Project Structure

```
poly-tui/
├── src/
│   ├── main.py          # Entry point & async orchestrator
│   ├── config.py        # Environment config loader
│   ├── auth.py          # Polymarket client authentication
│   ├── market.py        # Market window discovery (Gamma API)
│   ├── price_feed.py    # BTC price via Chainlink oracle on Polygon
│   ├── odds_feed.py     # UP/DOWN odds via CLOB API midpoints
│   ├── trader.py        # Live trade execution (FOK orders)
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
