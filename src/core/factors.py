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
    if len(close) < sma_long:
        return np.nan

    price = close.iloc[-1]
    sma_s = close.rolling(sma_short).mean().iloc[-1]
    sma_l = close.rolling(sma_long).mean().iloc[-1]

    if price > sma_s and price > sma_l:
        return 1.0
    elif price > sma_l:
        return 0.5
    else:
        return 0.0


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


def mean_reversion_score(
    close: pd.Series,
    rsi_period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
) -> float:
    rsi_val = rsi(close, rsi_period)
    if np.isnan(rsi_val):
        return np.nan

    if rsi_val < oversold:
        return 1.0
    elif rsi_val < 45:
        return 0.5
    elif rsi_val > overbought:
        return 0.0
    else:
        return 0.25
