import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import alpaca_trade_api as tradeapi

logger = logging.getLogger(__name__)

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

    def submit_order(self, ticker: str, side: str, notional: float) -> dict:
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
