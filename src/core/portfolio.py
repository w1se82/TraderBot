import logging
from dataclasses import dataclass

from src.core.scorer import ScoredETF

logger = logging.getLogger(__name__)


@dataclass
class Order:
    ticker: str
    side: str  # "buy" or "sell"
    notional: float  # dollar amount


def compute_target_weights(selected: list[ScoredETF], method: str = "equal_weight") -> dict[str, float]:
    if not selected:
        return {}

    if method == "equal_weight":
        w = 1.0 / len(selected)
        return {etf.ticker: w for etf in selected}

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
            sells.append(Order(ticker=ticker, side="sell", notional=round(abs(diff), 2)))
        else:
            buys.append(Order(ticker=ticker, side="buy", notional=round(diff, 2)))

    return sells + buys
