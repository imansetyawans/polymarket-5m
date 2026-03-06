"""
Rich TUI Dashboard — real-time updating terminal UI.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.align import Align

from src.logger import get_log_buffer

log = logging.getLogger("polybot")

WIB = timezone(timedelta(hours=7))

# ── Color palette ────────────────────────────────────────────────
ACCENT = "bright_cyan"
ACCENT2 = "bright_magenta"
UP_COLOR = "bright_green"
DOWN_COLOR = "bright_red"
DIM = "dim white"
WARN_COLOR = "bright_yellow"
BORDER = "bright_blue"


def _format_countdown(seconds: float) -> str:
    """Format seconds into MM:SS.mmm countdown string."""
    if seconds <= 0:
        return "[bright_red]CLOSED[/]"
    mins = int(seconds // 60)
    secs = seconds % 60
    if seconds <= 10:
        return f"[bright_red bold]{mins:02d}:{secs:06.3f}[/]"
    elif seconds <= 30:
        return f"[bright_yellow]{mins:02d}:{secs:06.3f}[/]"
    else:
        return f"[bright_green]{mins:02d}:{secs:06.3f}[/]"


def _make_header(state: dict) -> Panel:
    """Top banner with time and status."""
    now = datetime.now(WIB)
    time_str = now.strftime("%H:%M:%S.%f")[:-3]

    header = Text()
    header.append("  ⚡ POLYMARKET AUTO-TRADER", style="bold bright_cyan")

    if state.get("sim_mode"):
        header.append("  │  ", style="dim")
        header.append("🎮 SIM", style="bold bright_magenta")

    header.append("  │  ", style="dim")
    header.append(f"🕐 {time_str} WIB", style="bold white")
    header.append("  │  ", style="dim")

    window = state.get("window")
    if window:
        header.append("● ACTIVE", style="bold bright_green")
    else:
        header.append("○ IDLE", style="bold bright_yellow blink")

    return Panel(
        Align.center(header),
        style=BORDER,
        height=3,
    )


def _make_market_panel(state: dict) -> Panel:
    """Market window info with countdown."""
    window = state.get("window")

    if not window:
        content = Text("  Scanning for active btc-updown-5m window...\n", style=WARN_COLOR)
        content.append("  Retrying every 5 seconds", style=DIM)
        return Panel(content, title="[bold]📊 Market Window[/]", border_style=BORDER, height=8)

    seconds = state.get("seconds_to_close", 0)

    table = Table(show_header=False, expand=True, padding=(0, 1), box=None)
    table.add_column("label", style="bold", width=18)
    table.add_column("value")

    table.add_row("Window", f"[bold]{window.slug}[/]")
    table.add_row("Closes (WIB)", f"[{ACCENT}]{window.end_date.astimezone(WIB).strftime('%H:%M:%S')}[/]")
    table.add_row("Countdown", _format_countdown(seconds))
    table.add_row("Price to Beat", f"[bold bright_yellow]${window.price_to_beat:,.2f}[/]" if window.price_to_beat else "[dim]Loading...[/]")
    table.add_row("Market", f"[dim]polymarket.com/event/{window.slug}[/]")

    return Panel(table, title="[bold]📊 Market Window[/]", border_style=BORDER, height=8)


def _make_price_panel(state: dict) -> Panel:
    """BTC current price (Binance) and gap vs price-to-beat."""
    btc = state.get("btc_price")
    window = state.get("window")

    table = Table(show_header=False, expand=True, padding=(0, 1), box=None)
    table.add_column("label", style="bold", width=18)
    table.add_column("value")

    if btc is not None and btc > 0:
        table.add_row("BTC Price", f"[bold bright_white]${btc:,.2f}[/]")
    else:
        table.add_row("BTC Price", "[dim]Loading...[/]")

    if btc and window and window.price_to_beat:
        gap = btc - window.price_to_beat
        gap_abs = abs(gap)
        direction = "▲" if gap > 0 else "▼" if gap < 0 else "─"
        gap_color = UP_COLOR if gap > 0 else DOWN_COLOR if gap < 0 else DIM
        table.add_row("Gap", f"[{gap_color}]{direction} ${gap_abs:,.2f}[/]")

        trigger = config_gap_trigger()
        if gap_abs > trigger:
            table.add_row("Gap Status", f"[bold bright_red blink]⚠ TRIGGER (>${trigger})[/]")
        else:
            table.add_row("Gap Status", f"[dim]Normal (need >${trigger})[/]")
    else:
        table.add_row("Gap", "[dim]—[/]")

    return Panel(table, title="[bold]₿ BTC Price (Binance)[/]", border_style=BORDER, height=7)


def config_gap_trigger() -> float:
    from src import config
    return config.GAP_TRIGGER_USD


def _make_odds_panel(state: dict) -> Panel:
    """Quantitative Strategy Display."""
    up = state.get("up_odds", 0)
    down = state.get("down_odds", 0)
    
    p_true = state.get("p_true")
    edge = state.get("edge")
    ev = state.get("ev")
    side = state.get("signal_side")
    reason = state.get("signal_reason")

    table = Table(show_header=False, expand=True, padding=(0, 1), box=None)
    table.add_column("label", style="bold", width=18)
    table.add_column("value")

    # Raw Odds
    if up > down:
        up_style, down_style = f"bold {UP_COLOR}", DIM
    elif down > up:
        up_style, down_style = DIM, f"bold {DOWN_COLOR}"
    else:
        up_style = down_style = ACCENT

    table.add_row("UP / DOWN Odds", f"[{up_style}]{up:.4f}[/] / [{down_style}]{down:.4f}[/]" if (up or down) else "[dim]—[/]")

    # Quantitative Metrics
    if edge is not None and ev is not None:
        edge_pct = edge * 100
        edge_color = "bright_green" if edge > 0 else "bright_red"
        ev_color = "bright_green" if ev > 0 else "bright_red"
        
        table.add_row("Est. p_true", f"{p_true:.4f}" if p_true else "[dim]—[/]")
        table.add_row("Edge", f"[{edge_color}]{edge_pct:+.2f}%[/]")
        table.add_row("Expected Value", f"[{ev_color}]{ev:+.4f}[/]")
    else:
        table.add_row("Est. p_true", "[dim]—[/]")
        table.add_row("Edge", "[dim]—[/]")
        table.add_row("Expected Value", "[dim]—[/]")

    # Signal
    if side == "UP":
        signal_color = f"bold {UP_COLOR}"
        symbol = "⬆"
    elif side == "DOWN":
        signal_color = f"bold {DOWN_COLOR}"
        symbol = "⬇"
    else:
        signal_color = DIM
        symbol = "○"

    signal_text = f"[{signal_color}]{symbol} {side}[/]" if side else "[dim]Waiting...[/]"
    table.add_row("Target Side", signal_text)
    table.add_row("Signal Status", reason if reason else "[dim]Evaluating...[/]")

    return Panel(table, title="[bold]📈 Quant Strategy[/]", border_style=BORDER, height=9)


def _make_equity_panel(state: dict) -> Panel:
    """Total equity breakdown."""
    equity = state.get("equity", {})
    usdc = equity.get("usdc_balance", 0)
    winning = equity.get("winning_value", 0)
    total = equity.get("total", 0)

    table = Table(show_header=False, expand=True, padding=(0, 1), box=None)
    table.add_column("label", style="bold", width=18)
    table.add_column("value")

    table.add_row("USDC Balance", f"[bright_green]${usdc:,.2f}[/]")
    table.add_row("Unredeemed Wins", f"[bright_yellow]${winning:,.2f}[/]")
    table.add_row("─" * 14, "─" * 14)
    table.add_row("Total Equity", f"[bold bright_white]${total:,.2f}[/]")

    return Panel(table, title="[bold]💰 Equity[/]", border_style=BORDER, height=7)


def _make_positions_panel(state: dict) -> Panel:
    """Open positions table."""
    positions = state.get("positions", [])

    if not positions:
        content = Text("  No open positions", style=DIM)
        return Panel(content, title="[bold]📋 Positions[/]", border_style=BORDER, height=6)

    table = Table(expand=True, padding=(0, 1))
    table.add_column("Market", style=ACCENT, max_width=20)
    table.add_column("Side", justify="center", width=6)
    table.add_column("Size", justify="right", width=10)
    table.add_column("Status", justify="center", width=10)

    for pos in positions[:5]:  # Show last 5
        market = str(pos.get("market", pos.get("slug", "—")))[:20]
        side = str(pos.get("side", "—"))
        size = pos.get("size", pos.get("quantity", 0))
        size_str = f"${float(size):,.2f}" if size else "—"
        status = str(pos.get("status", pos.get("outcome", "open")))

        side_color = UP_COLOR if "buy" in side.lower() else DOWN_COLOR
        table.add_row(market, f"[{side_color}]{side}[/]", size_str, status)

    return Panel(table, title="[bold]📋 Positions[/]", border_style=BORDER)


def _make_trade_log_panel(state: dict) -> Panel:
    """Last trade result + recent log entries."""
    last_trade = state.get("last_trade", "No trades yet")

    log_buf = get_log_buffer()
    recent = list(log_buf)[-8:]  # Last 8 log entries

    content = Text()
    content.append("  Last Trade: ", style="bold")
    content.append(f"{last_trade}\n\n", style=ACCENT2)

    for entry in recent:
        content.append(f"  {entry}\n", style=DIM)

    return Panel(content, title="[bold]📝 Trade Log[/]", border_style=BORDER)


def build_layout(state: dict) -> Layout:
    """Compose the full dashboard layout from state dict."""
    layout = Layout()

    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=12),
    )

    # Header
    layout["header"].update(_make_header(state))

    # Body: 2 columns
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    # Left column: Market + BTC Price
    layout["left"].split_column(
        Layout(name="market", size=8),
        Layout(name="price", size=7),
        Layout(name="odds", size=7),
    )

    # Right column: Equity + Positions
    layout["right"].split_column(
        Layout(name="equity", size=7),
        Layout(name="positions"),
    )

    layout["market"].update(_make_market_panel(state))
    layout["price"].update(_make_price_panel(state))
    layout["odds"].update(_make_odds_panel(state))
    layout["equity"].update(_make_equity_panel(state))
    layout["positions"].update(_make_positions_panel(state))

    # Footer: Trade log
    layout["footer"].update(_make_trade_log_panel(state))

    return layout
