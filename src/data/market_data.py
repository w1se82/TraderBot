import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


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
