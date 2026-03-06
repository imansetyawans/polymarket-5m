"""
Main entry point — async orchestrator for the Polymarket auto-trade bot.

Usage:
    python -m src.main              # Run the bot
    python -m src.main --approve    # One-time token allowance setup
    python -m src.main --dry-run    # Dashboard only, no trading
    python -m src.main --sim        # Simulation with $10 virtual balance
    python -m src.main --sim 50     # Simulation with $50 virtual balance
"""

import sys
import asyncio
import argparse
import logging

from rich.live import Live
from rich.console import Console

from src.logger import setup_logging
from src.auth import create_client, approve_allowances
from src.market import market_discovery_loop
from src.price_feed import price_feed_loop
from src.trader import trade_loop
from src.positions import position_loop
from src.equity import get_total_equity
from src.odds_feed import odds_feed_loop
from src.sim_trader import sim_trade_loop, SimPortfolio
from src.dashboard import build_layout
from src import config

console = Console()


async def equity_update_loop(client, state: dict) -> None:
    """Periodically update equity data in the shared state."""
    while True:
        try:
            positions = state.get("positions", [])
            equity = get_total_equity(client, positions)
            state["equity"] = equity
        except Exception as e:
            logging.getLogger("polybot").error("Equity update error: %s", e)
        await asyncio.sleep(5)


async def dashboard_loop(state: dict) -> None:
    """Render the TUI dashboard at 500ms refresh rate."""
    with Live(
        build_layout(state),
        console=console,
        refresh_per_second=config.DASHBOARD_REFRESH_PER_SECOND,
        screen=True,
    ) as live:
        while True:
            live.update(build_layout(state))
            await asyncio.sleep(0.25)


async def run_bot(dry_run: bool = False, sim_balance: float = 0) -> None:
    """Main async runner — starts all concurrent loops."""
    log = logging.getLogger("polybot")

    # Shared state dict — all loops read/write here
    state: dict = {
        "window": None,
        "window_locked": False,
        "btc_price": 0.0,
        "up_odds": 0.0,
        "down_odds": 0.0,
        "gap": 0.0,
        "seconds_to_close": 0.0,
        "positions": [],
        "equity": {"usdc_balance": 0, "winning_value": 0, "total": 0},
        "last_trade": "No trades yet",
        "last_redeem": "",
        "sim_mode": False,
    }

    if sim_balance > 0:
        # ── SIMULATION MODE ──────────────────────────────────────
        portfolio = SimPortfolio(starting_balance=sim_balance)
        state["sim_mode"] = True
        state["equity"] = portfolio.get_equity_dict()
        log.info("Starting SIMULATION mode — virtual balance: $%.2f", sim_balance)

        tasks = [
            asyncio.create_task(market_discovery_loop(state)),
            asyncio.create_task(price_feed_loop(state)),
            asyncio.create_task(odds_feed_loop(state)),
            asyncio.create_task(sim_trade_loop(portfolio, state)),
            asyncio.create_task(dashboard_loop(state)),
        ]
    elif dry_run:
        log.info("Starting in DRY-RUN mode — dashboard only, no trading")
        tasks = [
            asyncio.create_task(market_discovery_loop(state)),
            asyncio.create_task(price_feed_loop(state)),
            asyncio.create_task(odds_feed_loop(state)),
            asyncio.create_task(dashboard_loop(state)),
        ]
    else:
        config.validate_trading_config()
        log.info("Initializing Polymarket client...")
        client = create_client()
        log.info("Client ready — starting bot")

        tasks = [
            asyncio.create_task(market_discovery_loop(state)),
            asyncio.create_task(price_feed_loop(state)),
            asyncio.create_task(odds_feed_loop(state)),
            asyncio.create_task(trade_loop(client, state)),
            asyncio.create_task(position_loop(client, state)),
            asyncio.create_task(equity_update_loop(client, state)),
            asyncio.create_task(dashboard_loop(state)),
        ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log.info("Bot shutting down...")
    except KeyboardInterrupt:
        log.info("Keyboard interrupt — shutting down")
    finally:
        for t in tasks:
            t.cancel()
        log.info("All tasks cancelled — goodbye!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Polymarket BTC Auto-Trade Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main              Run the bot (live trading)
  python -m src.main --approve    Set token allowances (one-time)
  python -m src.main --dry-run    Dashboard only, no trading
  python -m src.main --sim        Simulation with $10 virtual balance
  python -m src.main --sim 50     Simulation with $50 virtual balance
        """,
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Set token allowances for EOA wallet (one-time setup)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Start dashboard without trading (no auth required)",
    )
    parser.add_argument(
        "--sim",
        nargs="?",
        const=10.0,
        type=float,
        metavar="BALANCE",
        help="Run simulation with virtual balance (default: $10)",
    )
    args = parser.parse_args()

    # Setup logging
    setup_logging()
    log = logging.getLogger("polybot")

    if args.approve:
        console.print("[bold cyan]Setting up token allowances...[/]")
        approve_allowances()
        console.print("[bold green]Done! You can now run the bot.[/]")
        return

    if args.sim is not None:
        console.print(f"[bold magenta]🎮 Starting SIMULATION mode — ${args.sim:.2f} virtual balance[/]")
    elif args.dry_run:
        console.print("[bold yellow]Starting in dry-run mode...[/]")

    console.print("[bold cyan]⚡ Polymarket Auto-Trader starting...[/]")

    try:
        asyncio.run(run_bot(dry_run=args.dry_run, sim_balance=args.sim or 0))
    except KeyboardInterrupt:
        console.print("\n[bold red]Shutdown complete.[/]")
        sys.exit(0)


if __name__ == "__main__":
    main()
