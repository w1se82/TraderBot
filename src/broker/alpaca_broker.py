import csv
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import alpaca_trade_api as tradeapi

logger = logging.getLogger(__name__)

PDT_MAX_DAY_TRADES = 3
PDT_WINDOW_DAYS = 5

TRADE_LOG = Path(__file__).resolve().parent.parent.parent / "logs" / "trades.csv"


@dataclass
class AccountInfo:
    equity: float
    cash: float
    buying_power: float


@dataclass
class PositionInfo:
    qty: float
    market_value: float
    current_price: float


class AlpacaBroker:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True, base_url: str = ""):
        if not base_url:
            base_url = (
                "https://paper-api.alpaca.markets" if paper
                else "https://api.alpaca.markets"
            )
        self.api = tradeapi.REST(api_key, secret_key, base_url, api_version="v2")
        self._paper = paper
        logger.info(f"Connected to Alpaca ({'paper' if paper else 'LIVE'})")

    def get_account(self) -> AccountInfo:
        acct = self.api.get_account()
        return AccountInfo(
            equity=float(acct.equity),
            cash=float(acct.cash),
            buying_power=float(acct.buying_power),
        )

    def get_positions(self) -> dict[str, PositionInfo]:
        positions = self.api.list_positions()
        return {
            p.symbol: PositionInfo(
                qty=float(p.qty),
                market_value=float(p.market_value),
                current_price=float(p.current_price),
            )
            for p in positions
        }

    def submit_order(self, ticker: str, side: str, notional: float) -> dict | None:
        if side == "sell" and self._is_day_trade(ticker):
            used = self._count_day_trades_this_window()
            if used >= PDT_MAX_DAY_TRADES:
                logger.warning(
                    "PDT limit reached (%d/%d day trades in last %d days) — "
                    "skipping sell %s to avoid pattern day trader flag",
                    used, PDT_MAX_DAY_TRADES, PDT_WINDOW_DAYS, ticker,
                )
                return None

        logger.info(f"Submitting {side} ${notional:.2f} of {ticker}")
        order = self.api.submit_order(
            symbol=ticker,
            notional=round(notional, 2),
            side=side,
            type="market",
            time_in_force="day",
        )
        self._log_trade(ticker, side, notional)
        return {"id": order.id, "status": order.status, "symbol": order.symbol}

    def _is_day_trade(self, ticker: str) -> bool:
        """True als ticker vandaag ook al gekocht is (= zou een day trade worden)."""
        if not TRADE_LOG.exists():
            return False
        today = date.today().isoformat()
        with open(TRADE_LOG, newline="") as f:
            for row in csv.DictReader(f):
                if row["ticker"] == ticker and row["side"] == "buy" and row["timestamp"].startswith(today):
                    return True
        return False

    def _count_day_trades_this_window(self) -> int:
        """Tel het aantal day trades (koop+verkoop zelfde ticker zelfde dag) in de laatste 5 dagen."""
        if not TRADE_LOG.exists():
            return 0
        cutoff = (date.today() - timedelta(days=PDT_WINDOW_DAYS)).isoformat()
        # Groepeer trades per (datum, ticker, side)
        trades: dict[tuple, bool] = {}
        with open(TRADE_LOG, newline="") as f:
            for row in csv.DictReader(f):
                day = row["timestamp"][:10]
                if day < cutoff:
                    continue
                trades[(day, row["ticker"], row["side"])] = True
        # Dag trade = zowel buy als sell aanwezig voor zelfde ticker op zelfde dag
        day_trades = 0
        days_tickers = {(d, t) for (d, t, s) in trades if s == "sell"}
        for (d, t) in days_tickers:
            if (d, t, "buy") in trades:
                day_trades += 1
        return day_trades

    def liquidate_all(self) -> list[dict]:
        logger.warning("Liquidating ALL positions")
        positions = self.api.list_positions()
        results = []
        for p in positions:
            order = self.api.close_position(p.symbol)
            self._log_trade(p.symbol, "sell", float(p.market_value))
            results.append({"id": order.id, "symbol": p.symbol})
        return results

    def _log_trade(self, ticker: str, side: str, notional: float) -> None:
        TRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
        write_header = not TRADE_LOG.exists()
        with open(TRADE_LOG, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["timestamp", "ticker", "side", "notional"])
            writer.writerow([datetime.now().isoformat(), ticker, side, f"{notional:.2f}"])
