import numpy as np
import pandas as pd


def momentum_score(close: pd.Series, windows: list[int], weights: list[float]) -> float:
    returns = []
    for w in windows:
        if len(close) < w:
            return np.nan
        ret = (close.iloc[-1] / close.iloc[-w]) - 1
        returns.append(ret)

    return sum(r * w for r, w in zip(returns, weights))


def volatility_score(close: pd.Series, window: int = 63) -> float:
    if len(close) < window:
        return np.nan
    daily_returns = close.pct_change().dropna()
    vol = daily_returns.rolling(window).std().iloc[-1] * np.sqrt(252)
    return vol


def trend_score(close: pd.Series, sma_short: int = 50, sma_long: int = 200) -> float:
    """Returns continuous trend strength: how far price sits above/below the long-term SMA.

    Raw return value (positive = above SMA200, negative = below). Caller is
    responsible for cross-sectional percentile ranking before use in scoring.
    """
    if len(close) < sma_long:
        return np.nan

    price = close.iloc[-1]
    sma_l = close.rolling(sma_long).mean().iloc[-1]
    return (price / sma_l) - 1


def rsi(close: pd.Series, period: int = 14) -> float:
    if len(close) < period + 1:
        return np.nan

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
