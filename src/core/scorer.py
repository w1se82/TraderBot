import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core.factors import (
    momentum_score,
    rsi,
    trend_score,
    volatility_score,
)

logger = logging.getLogger(__name__)


@dataclass
class ScoredETF:
    ticker: str
    composite: float
    factors: dict[str, float]   # normalised 0–1 scores
    raw: dict[str, float] = None  # actual values (RSI, vol%, returns)


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
) -> tuple[list[ScoredETF], list[ScoredETF]]:
    """Return (selected, all_ranked) where selected is the top N ETFs."""
    factor_cfg = config["factors"]
    score_cfg = config["scoring"]

    tickers = list(price_data.keys())
    raw_momentum, raw_vol, raw_trend = [], [], []
    raw_values: list[dict] = []

    for ticker in tickers:
        close = price_data[ticker]["Close"]
        windows = factor_cfg["momentum"]["windows"]
        weights = factor_cfg["momentum"]["weights"]

        raw_momentum.append(momentum_score(close, windows, weights))
        raw_vol.append(volatility_score(
            close,
            factor_cfg["volatility"]["window_short"],
            factor_cfg["volatility"]["window_long"],
        ))
        raw_trend.append(trend_score(close, factor_cfg["trend"]["sma_long"]))

        # Collect raw (human-readable) values for the AI prompt
        # Annualized vol computed separately (not the relative ratio used for scoring)
        _daily = close.pct_change().dropna()
        _vol_ann = _daily.rolling(factor_cfg["volatility"]["window_long"]).std().iloc[-1] * np.sqrt(252)
        vol_pct = float(_vol_ann) if not np.isnan(_vol_ann) else float("nan")
        rsi_val = rsi(close)
        ret_1m = float((close.iloc[-1] / close.iloc[-22] - 1) * 100) if len(close) >= 22 else float("nan")
        ret_3m = float((close.iloc[-1] / close.iloc[-63] - 1) * 100) if len(close) >= 63 else float("nan")
        ret_6m = float((close.iloc[-1] / close.iloc[-126] - 1) * 100) if len(close) >= 126 else float("nan")
        raw_values.append({
            "vol_pct": round(vol_pct * 100, 1) if not np.isnan(float(vol_pct)) else None,
            "rsi": round(rsi_val, 1) if not np.isnan(rsi_val) else None,
            "return_1m": round(ret_1m, 2) if not np.isnan(ret_1m) else None,
            "return_3m": round(ret_3m, 2) if not np.isnan(ret_3m) else None,
            "return_6m": round(ret_6m, 2) if not np.isnan(ret_6m) else None,
        })

    mom_ranked = _percentile_rank(raw_momentum)
    vol_ranked = [1.0 - r if not np.isnan(r) else np.nan for r in _percentile_rank(raw_vol)]
    trend_ranked = _percentile_rank(raw_trend)

    results = []
    for i, ticker in enumerate(tickers):
        factors = {
            "momentum": mom_ranked[i],
            "volatility": vol_ranked[i],
            "trend": trend_ranked[i],
        }

        if any(np.isnan(v) for v in factors.values()):
            logger.warning(f"{ticker}: incomplete factor data, skipping")
            continue

        composite = (
            score_cfg["momentum_weight"] * factors["momentum"]
            + score_cfg["volatility_weight"] * factors["volatility"]
            + score_cfg["trend_weight"] * factors["trend"]
        )

        results.append(ScoredETF(
            ticker=ticker,
            composite=composite,
            factors=factors,
            raw=raw_values[i],
        ))

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
            f"composite={r.composite:.3f}{marker}"
        )

    return selected, results
