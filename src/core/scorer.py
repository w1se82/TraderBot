import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core.factors import (
    mean_reversion_score,
    momentum_score,
    trend_score,
    volatility_score,
)

logger = logging.getLogger(__name__)


@dataclass
class ScoredETF:
    ticker: str
    composite: float
    factors: dict[str, float]


def _percentile_rank(values: list[float]) -> list[float]:
    arr = np.array(values, dtype=float)
    valid = ~np.isnan(arr)
    n = int(valid.sum())
    ranks = np.full_like(arr, np.nan)
    if n == 0:
        return ranks.tolist()
    if n == 1:
        ranks[valid] = 0.5
        return ranks.tolist()
    sorted_vals = np.sort(arr[valid])
    for i, v in enumerate(arr):
        if np.isnan(v):
            continue
        pos = np.searchsorted(sorted_vals, v, side="right")
        ranks[i] = (pos - 1) / (n - 1)
    return ranks.tolist()


def rank_etfs(
    price_data: dict[str, pd.DataFrame],
    config: dict,
) -> list[ScoredETF]:
    factor_cfg = config["factors"]
    score_cfg = config["scoring"]

    tickers = list(price_data.keys())
    raw_momentum = []
    raw_vol = []
    raw_trend = []
    raw_mr = []

    for ticker in tickers:
        close = price_data[ticker]["Close"]

        raw_momentum.append(momentum_score(
            close,
            factor_cfg["momentum"]["windows"],
            factor_cfg["momentum"]["weights"],
        ))
        raw_vol.append(volatility_score(close, factor_cfg["volatility"]["window"]))
        raw_trend.append(trend_score(
            close, factor_cfg["trend"]["sma_short"], factor_cfg["trend"]["sma_long"]
        ))
        raw_mr.append(mean_reversion_score(
            close,
            factor_cfg["mean_reversion"]["rsi_period"],
            factor_cfg["mean_reversion"]["oversold_threshold"],
            factor_cfg["mean_reversion"]["overbought_threshold"],
        ))

    mom_ranked = _percentile_rank(raw_momentum)
    vol_ranked = [1.0 - r if not np.isnan(r) else np.nan for r in _percentile_rank(raw_vol)]

    results = []
    for i, ticker in enumerate(tickers):
        factors = {
            "momentum": mom_ranked[i],
            "volatility": vol_ranked[i],
            "trend": raw_trend[i],
            "mean_reversion": raw_mr[i],
        }

        if any(np.isnan(v) for v in factors.values()):
            logger.warning(f"{ticker}: incomplete factor data, skipping")
            continue

        composite = (
            score_cfg["momentum_weight"] * factors["momentum"]
            + score_cfg["volatility_weight"] * factors["volatility"]
            + score_cfg["trend_weight"] * factors["trend"]
            + score_cfg["mean_reversion_weight"] * factors["mean_reversion"]
        )

        results.append(ScoredETF(ticker=ticker, composite=composite, factors=factors))

    results.sort(key=lambda x: x.composite, reverse=True)

    max_holdings = config["portfolio"]["max_holdings"]
    selected = results[:max_holdings]

    logger.info("ETF Rankings:")
    for r in results:
        marker = " <--" if r in selected else ""
        logger.info(
            f"  {r.ticker:5s}  mom={r.factors['momentum']:.2f}  "
            f"vol={r.factors['volatility']:.2f}  "
            f"trend={r.factors['trend']:.2f}  "
            f"mr={r.factors['mean_reversion']:.2f}  "
            f"composite={r.composite:.3f}{marker}"
        )

    return selected
