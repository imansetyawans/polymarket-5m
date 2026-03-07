"""
Quantitative trading strategy logic.
Calculates win probability (p_true), edge, Expected Value (EV), and Kelly criterion size.
"""

import math
from dataclasses import dataclass
from typing import Optional

# Standard normal cumulative distribution function
def norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


@dataclass
class TradeSignal:
    side: str
    price: float
    p_true: float
    edge: float
    ev: float
    kelly_size: float
    should_trade: bool
    reason: str


def estimate_p_true(gap: float, seconds_remaining: float, sigma_per_sec: float) -> float:
    """
    Estimate true probability of UP winning using a normal distribution model.
    gap = current_btc_price - price_to_beat (positive means UP is winning)
    """
    if seconds_remaining <= 0:
        return 1.0 if gap > 0 else 0.0 if gap < 0 else 0.5
        
    # Standard deviation over remaining time
    # e.g. 2.50 * sqrt(30) = $13.69
    volatility = sigma_per_sec * math.sqrt(seconds_remaining)
    
    if volatility == 0:
        return 1.0 if gap > 0 else 0.0 if gap < 0 else 0.5
        
    # Z-score: how many standard deviations away is the gap from 0
    z = gap / volatility
    
    # Probability that the final price stays above price_to_beat
    return norm_cdf(z)


def calculate_edge(p_true: float, market_price: float) -> float:
    """Edge = our estimated probability - market implied probability"""
    return p_true - market_price


def calculate_ev(p_true: float, market_price: float) -> float:
    """
    Expected Value per $1 wagered.
    EV = (p_true * profit) - (q_true * loss)
    Profit on $1 is (1/market_price - 1). Loss is $1.
    """
    if market_price <= 0 or market_price >= 1:
        return 0.0
        
    profit_if_win = (1.0 / market_price) - 1.0
    q_true = 1.0 - p_true
    
    return (p_true * profit_if_win) - (q_true * 1.0)


def kelly_size(p_true: float, market_price: float, balance: float, fraction: float = 0.5) -> float:
    """
    Calculate optimal bet size using Kelly Criterion.
    f* = (p * b - q) / b
    Where b is the net decimal odds received (profit on $1 bet).
    """
    if market_price <= 0 or market_price >= 1 or balance <= 0:
        return 0.0
        
    b = (1.0 / market_price) - 1.0
    q_true = 1.0 - p_true
    
    # Kelly fraction
    f_star = (p_true * b - q_true) / b
    
    # If edge is negative, Kelly says don't bet (f* <= 0)
    if f_star <= 0:
        return 0.0
        
    # Capping size
    raw_size = balance * bet_fraction
    
    # Enforce Polymarket minimum order size if an edge exists
    if 0 < raw_size < 1.0:
        raw_size = 1.0
        
    return float(round(raw_size, 2))


def evaluate_market(
    btc_price: float, 
    price_to_beat: float, 
    seconds_remaining: float,
    up_odds: float,
    down_odds: float,
    balance: float,
    sigma_per_sec: float,
    edge_threshold: float,
    kelly_fraction: float
) -> Optional[TradeSignal]:
    """
    Evaluate the market to generate a trade signal.
    Determines which side to bet on based on highest edge.
    """
    if seconds_remaining < 0 or btc_price <= 0 or price_to_beat <= 0:
        return None
        
    if up_odds <= 0 and down_odds <= 0:
        return None

    gap = btc_price - price_to_beat
    p_true_up = estimate_p_true(gap, seconds_remaining, sigma_per_sec)
    p_true_down = 1.0 - p_true_up

    # Evaluate UP side
    edge_up = calculate_edge(p_true_up, up_odds) if up_odds > 0 else -1
    edge_down = calculate_edge(p_true_down, down_odds) if down_odds > 0 else -1

    # Choose the side with the better edge
    if edge_up >= edge_down and up_odds > 0:
        side = "UP"
        price = up_odds
        p_true = p_true_up
        edge = edge_up
    elif down_odds > 0:
        side = "DOWN"
        price = down_odds
        p_true = p_true_down
        edge = edge_down
    else:
        return None

    # Calculate EV and Kelly size
    ev = calculate_ev(p_true, price)
    k_size = kelly_size(p_true, price, balance, kelly_fraction)

    # Trading rules
    should_trade = False
    reason = ""
    
    if edge < edge_threshold:
        reason = f"Edge {edge:.4f} < {edge_threshold}"
    elif ev <= 0:
        reason = f"Negative EV ({ev:.4f})"
    elif k_size <= 0:
        reason = "Kelly size is zero"
    else:
        should_trade = True
        reason = "Trade criteria met"

    return TradeSignal(
        side=side,
        price=price,
        p_true=p_true,
        edge=edge,
        ev=ev,
        kelly_size=k_size,
        should_trade=should_trade,
        reason=reason
    )
