# ⚡ Polymarket BTC Auto-Trader

A terminal-based (TUI) auto-trading bot for [Polymarket](https://polymarket.com) **Bitcoin Up or Down — 5 Minutes** markets.

Built with Python, Rich, and the Polymarket CLOB API.

![Dashboard Preview](https://img.shields.io/badge/status-active-brightgreen) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

---

## Features

- 🎯 **Auto-trades** BTC Up/Down 5-minute windows on Polymarket
- 📊 **Real-time TUI dashboard** with countdown, edge metrics, BTC price, equity
- 🧠 **Quantitative Strategy** — calculates *p_true*, Edge, Expected Value (EV), and Kelly Criterion
- ⚡ **Lightning-fast BTC feed** — 1-second millisecond accurate price via Binance Public API
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

Edit `.env` with your credentials and strategy limits:

```env
# Required for live trading only (not needed for --sim or --dry-run)
POLY_PRIVATE_KEY=your_private_key_here
POLY_FUNDER_ADDRESS=your_wallet_address_here

# === Trade Settings ===
TRADE_AMOUNT_MODE=percent       # "percent" or "fixed"
TRADE_AMOUNT_VALUE=50           # max wallet percent or fixed USDC to use
GAP_TRIGGER_USD=120             # gap trigger threshold in USD
ENTRY_SECONDS_BEFORE_CLOSE=5    # primary entry seconds before close
GAP_TRIGGER_SECONDS_BEFORE_CLOSE=60  # secondary trigger window in seconds

# === Quantitative Strategy ===
EDGE_THRESHOLD=0.07             # Minimum edge to enter a trade (0.07 = 7%)
KELLY_FRACTION=0.5              # Fraction of Kelly Criterion (0.5 = Half-Kelly)
BTC_VOLATILITY_PER_SEC=2.50     # Estimated BTC volatility per second in USD
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

## How It Works

### 1. Market Discovery
The bot continuously scans for active `btc-updown-5m-{timestamp}` windows on Polymarket's Gamma API. It parses the exactly timed 5-minute epochs and finds the target market.

### 2. Real-time Price Data
- **BTC Price**: Fetched asynchronously every 1.0 seconds directly from the **Binance Public API** (`api/v3/ticker/price`) ensuring millisecond reaction times without on-chain RPC lag.
- **Price to Beat**: Fetched from the previous window's `eventMetadata.priceToBeat` via Gamma API, matching exactly what Polymarket displays.

### 3. Quantitative Edge-EV-Kelly Strategy
When a trigger window approaches (T-60s Gap or T-5s Primary execution), the bot evaluates the market rigorously:

1. **`p_true` Estimation**: Estimates the actual probability of UP winning using a normal distribution volatility model based on the BTC gap and seconds remaining (`z = gap / (σ_sec × √seconds)`).
2. **Edge Calculation**: `Edge = p_true - Market Implied Probability`. The bot ONLY trades if the math dictates an edge greater than the configured `EDGE_THRESHOLD` (e.g., > 7%).
3. **EV Filter**: Calculates Expected Value. Refuses any trade with `EV < 0`.
4. **Dynamic Bet Sizing**: If a trade passes all filters, the bot calculates the exact mathematically optimal bet fraction using the **Kelly Criterion**, scaling the position based on the size of the Edge.

### 4. Simulation Engine
- Uses **live market data** — live windows, live Binance price, live CLOB odds.
- Executes against a **virtual balance** (default $10).
- Polls the Polymarket outcome resolution (Gamma API `outcomePrices`) perfectly, determining wins/losses exactly as the blockchain oracle will.
- Tracks **W/L record, P&L, accuracy, and bankroll**.

---

## Project Structure

```
poly-tui/
├── src/
│   ├── main.py          # Entry point & async orchestrator
│   ├── config.py        # Environment config loader
│   ├── strategy.py      # Core math formulas (Edge, EV, p_true, Kelly)
│   ├── auth.py          # Polymarket client authentication
│   ├── market.py        # Market window discovery (Gamma API)
│   ├── price_feed.py    # Async real-time BTC ticker via Binance
│   ├── odds_feed.py     # UP/DOWN odds via CLOB API midpoints
│   ├── trader.py        # Live trade execution applying Kelly strategy
│   ├── sim_trader.py    # Simulation engine replicating live logic
│   ├── positions.py     # Live position tracking & redemption
│   ├── equity.py        # USDC balance & equity calculation
│   ├── dashboard.py     # Rich quantitative TUI dashboard renderer
│   └── logger.py        # Logging setup with in-memory buffer
├── .env.example         # Environment template
├── requirements.txt     # Python dependencies
└── README.md
```

---

## Requirements

- Python 3.10+
- Polygon wallet with USDC (for live trading only)
- Internet connection (Binance API access)

### Key Dependencies

| Package | Purpose |
|---------|---------|
| `py-clob-client` | Polymarket CLOB API live execution |
| `aiohttp` | Lightning-fast async HTTP for APIs |
| `rich` | Terminal UI dashboard rendering |
| `python-dotenv` | Environment configuration |

---

## License

MIT
