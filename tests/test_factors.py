import numpy as np
import pandas as pd
import pytest

from src.core.factors import (
    momentum_score,
    rsi,
    trend_score,
    volatility_score,
)


class TestMomentum:
    def test_uptrend_positive(self, uptrend_close):
        score = momentum_score(uptrend_close, [21, 63, 126], [0.33, 0.33, 0.34])
        assert score > 0

    def test_downtrend_negative(self, downtrend_close):
        score = momentum_score(downtrend_close, [21, 63, 126], [0.33, 0.33, 0.34])
        assert score < 0

    def test_insufficient_data(self):
        short = pd.Series([100, 101, 102])
        score = momentum_score(short, [21], [1.0])
        assert np.isnan(score)


class TestVolatility:
    def test_flat_low_vol(self, flat_close):
        vol = volatility_score(flat_close, window=63)
        assert 0 < vol < 0.10  # annualized vol under 10%

    def test_uptrend_reasonable_vol(self, uptrend_close):
        vol = volatility_score(uptrend_close, window=63)
        assert 0 < vol < 0.50

    def test_insufficient_data(self):
        short = pd.Series([100, 101])
        assert np.isnan(volatility_score(short, window=63))


class TestTrend:
    def test_strong_uptrend(self, uptrend_close):
        score = trend_score(uptrend_close, 50, 200)
        assert score > 0  # price above SMA200

    def test_strong_downtrend(self, downtrend_close):
        score = trend_score(downtrend_close, 50, 200)
        assert score < 0  # price below SMA200

    def test_insufficient_data(self):
        short = pd.Series(range(100))
        assert np.isnan(trend_score(short, 50, 200))


class TestRSI:
    def test_range(self, uptrend_close):
        val = rsi(uptrend_close)
        assert 0 <= val <= 100

    def test_constant_gains(self):
        prices = pd.Series(np.linspace(100, 200, 30))
        val = rsi(prices, 14)
        assert val > 70  # overbought

    def test_constant_losses(self):
        prices = pd.Series(np.linspace(200, 100, 30))
        val = rsi(prices, 14)
        assert val < 30  # oversold


