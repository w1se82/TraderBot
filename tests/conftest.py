import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def uptrend_close() -> pd.Series:
    """300 days of steadily rising prices: 100 → ~182."""
    np.random.seed(42)
    base = 100 * np.cumprod(1 + np.random.normal(0.002, 0.005, 300))
    return pd.Series(base, name="Close")


@pytest.fixture
def downtrend_close() -> pd.Series:
    """300 days of steadily falling prices: 100 → ~55."""
    np.random.seed(42)
    base = 100 * np.cumprod(1 + np.random.normal(-0.002, 0.005, 300))
    return pd.Series(base, name="Close")


@pytest.fixture
def flat_close() -> pd.Series:
    """300 days of flat prices with low volatility."""
    np.random.seed(42)
    base = 100 * np.cumprod(1 + np.random.normal(0, 0.002, 300))
    return pd.Series(base, name="Close")


@pytest.fixture
def sample_universe(uptrend_close, downtrend_close, flat_close) -> dict[str, pd.DataFrame]:
    """5 fake ETFs with different characteristics."""
    def make_df(close_series: pd.Series) -> pd.DataFrame:
        return pd.DataFrame({
            "Open": close_series * 0.999,
            "High": close_series * 1.005,
            "Low": close_series * 0.995,
            "Close": close_series,
            "Volume": np.random.randint(1_000_000, 10_000_000, len(close_series)),
        })

    np.random.seed(10)
    strong_up = 100 * np.cumprod(1 + np.random.normal(0.003, 0.008, 300))
    np.random.seed(20)
    volatile = 100 * np.cumprod(1 + np.random.normal(0.001, 0.020, 300))

    return {
        "UP": make_df(uptrend_close),
        "DOWN": make_df(downtrend_close),
        "FLAT": make_df(flat_close),
        "STRONG": make_df(pd.Series(strong_up)),
        "VOLATILE": make_df(pd.Series(volatile)),
    }
