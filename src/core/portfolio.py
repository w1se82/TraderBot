import csv
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.scorer import ScoredETF

logger = logging.getLogger(__name__)

PORTFOLIO_HISTORY = Path(__file__).resolve().parent.parent.parent / "logs" / "portfolio_history.csv"


def record_snapshot(portfolio_value: float, initial_capital: float) -> None:
    """Record one portfolio snapshot per day. Overwrites earlier entry for today."""
    PORTFOLIO_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now().date().isoformat()

    rows = []
    if PORTFOLIO_HISTORY.exists():
        with open(PORTFOLIO_HISTORY, newline="") as f:
            reader = csv.DictReader(f)
            rows = [r for r in reader if not r["timestamp"].startswith(today)]

    with open(PORTFOLIO_HISTORY, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "portfolio_value", "initial_capital"])
        for r in rows:
            writer.writerow([r["timestamp"], r["portfolio_value"], r["initial_capital"]])
        writer.writerow([datetime.now().isoformat(), f"{portfolio_value:.2f}", f"{initial_capital:.2f}"])


@dataclass
class Order:
    ticker: str
    side: str  # "buy" or "sell"
    notional: float  # dollar amount
    full_exit: bool = False  # if True, close entire position (avoids qty rounding errors)


def compute_target_weights(selected: list[ScoredETF], method: str = "equal_weight") -> dict[str, float]:
    if not selected:
        return {}

    if method == "equal_weight":
        w = 1.0 / len(selected)
        return {etf.ticker: w for etf in selected}

    if method == "score_proportional":
        total = sum(etf.composite for etf in selected)
        return {etf.ticker: etf.composite / total for etf in selected}

    raise ValueError(f"Unknown sizing method: {method}")


def needs_rebalance(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    threshold: float = 0.05,
) -> bool:
    all_tickers = set(current_weights) | set(target_weights)
    for ticker in all_tickers:
        cur = current_weights.get(ticker, 0.0)
        tgt = target_weights.get(ticker, 0.0)
        if abs(cur - tgt) > threshold:
            return True
    return False


def generate_orders(
    current_positions: dict[str, float],
    target_weights: dict[str, float],
    total_equity: float,
    min_trade_value: float = 1.0,
) -> list[Order]:
    target_values = {t: w * total_equity for t, w in target_weights.items()}
    all_tickers = set(current_positions) | set(target_values)

    sells = []
    buys = []

    for ticker in all_tickers:
        current = current_positions.get(ticker, 0.0)
        target = target_values.get(ticker, 0.0)
        diff = target - current

        if abs(diff) < min_trade_value:
            continue

        if diff < 0:
            full_exit = target_values.get(ticker, 0.0) == 0.0
            sells.append(Order(ticker=ticker, side="sell", notional=math.floor(abs(diff) * 100) / 100, full_exit=full_exit))
        else:
            buys.append(Order(ticker=ticker, side="buy", notional=math.floor(diff * 100) / 100))

    return sells + buys
