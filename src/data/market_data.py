import logging
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class MacroSnapshot:
    vix: float                # CBOE Volatility Index
    yield_10y: float          # US 10-year Treasury yield (%)
    dxy: float                # US Dollar Index
    vix_1m_change: float      # VIX change over past month (pts)
    yield_1m_change: float    # 10Y yield change over past month (bps)
    spy_1m_return: float      # SPY 1-month return as market proxy (%)


def fetch_prices(tickers: list[str], days: int = 252) -> dict[str, pd.DataFrame]:
    calendar_days = int(days * 1.5) + 30
    period = f"{calendar_days}d"

    logger.info(f"Fetching {days} trading days of data for {len(tickers)} ETFs")

    raw = yf.download(tickers, period=period, group_by="ticker", progress=False)

    result: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = raw.copy()
            else:
                df = raw[ticker].copy()

            df = df.dropna(subset=["Close"])

            if len(df) < days:
                logger.warning(
                    f"{ticker}: only {len(df)} bars (need {days}), skipping"
                )
                continue

            df = df.tail(days)
            result[ticker] = df
            logger.debug(f"{ticker}: {len(df)} bars loaded")

        except Exception as e:
            logger.warning(f"{ticker}: failed to process data: {e}")
            continue

    logger.info(f"Successfully loaded data for {len(result)}/{len(tickers)} ETFs")
    return result


def fetch_macro() -> MacroSnapshot | None:
    """Fetch macro indicators: VIX, 10Y yield, DXY, SPY as market proxy."""
    try:
        raw = yf.download(
            ["^VIX", "^TNX", "DX-Y.NYB", "SPY"],
            period="60d",
            group_by="ticker",
            progress=False,
        )

        def _last(ticker: str) -> pd.Series:
            return raw[ticker]["Close"].dropna()

        vix = _last("^VIX")
        tnx = _last("^TNX")
        dxy = _last("DX-Y.NYB")
        spy = _last("SPY")

        snapshot = MacroSnapshot(
            vix=round(float(vix.iloc[-1]), 2),
            yield_10y=round(float(tnx.iloc[-1]), 3),
            dxy=round(float(dxy.iloc[-1]), 2),
            vix_1m_change=round(float(vix.iloc[-1] - vix.iloc[-22]), 2) if len(vix) >= 22 else 0.0,
            yield_1m_change=round((float(tnx.iloc[-1] - tnx.iloc[-22])) * 100, 1) if len(tnx) >= 22 else 0.0,
            spy_1m_return=round(float((spy.iloc[-1] / spy.iloc[-22] - 1) * 100), 2) if len(spy) >= 22 else 0.0,
        )
        logger.info(
            f"Macro: VIX={snapshot.vix} ({snapshot.vix_1m_change:+.1f}), "
            f"10Y={snapshot.yield_10y}% ({snapshot.yield_1m_change:+.0f}bps), "
            f"DXY={snapshot.dxy}, SPY 1m={snapshot.spy_1m_return:+.1f}%"
        )
        return snapshot

    except Exception as e:
        logger.warning(f"Failed to fetch macro data: {e}")
        return None
