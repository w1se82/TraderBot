import asyncio
import json
import logging
import math
import os
import shutil
from datetime import date
from pathlib import Path
from typing import AsyncIterator

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from src.ai.explainer import build_prompt
from src.broker.alpaca_broker import AlpacaBroker
from src.config import load_config
from src.broker.alpaca_broker import AlpacaBroker
from src.core.portfolio import compute_target_weights, generate_orders, needs_rebalance, record_snapshot
from src.core.risk import DrawdownMonitor
from src.core.scorer import rank_etfs
from src.data.market_data import fetch_prices, fetch_macro

app = FastAPI(title="TraderBot")
logger = logging.getLogger(__name__)

_STATIC = os.path.join(os.path.dirname(__file__), "static")
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"

_SETTINGS_ALLOWED = {
    "etfs": None,  # full list replacement
    "portfolio": {"max_holdings", "sizing_method", "rebalance_threshold"},
    "scoring": {"momentum_weight", "volatility_weight", "trend_weight"},
    "risk": {"max_drawdown", "cooldown_days"},
    "broker": {"paper_trading"},
}


def _load_risk_state() -> dict:
    state_path = "logs/risk_state.json"
    if os.path.exists(state_path):
        with open(state_path) as f:
            return json.load(f)
    return {}


def _make_claude_cmd() -> list[str]:
    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise RuntimeError("claude CLI not found in PATH")
    return [
        claude_bin,
        "--output-format", "stream-json",
        "--verbose",
        "--setting-sources", "",
        "--input-format", "stream-json",
        "--allowedTools", "WebSearch",
        "--max-turns", "3",
    ]


async def _stream_claude(prompt: str, project_root: str) -> AsyncIterator[str]:
    """Yield text chunks from the Claude CLI."""
    clean_env = {k: v for k, v in os.environ.items()
                 if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE")}

    input_msg = json.dumps({
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}
    }) + "\n"

    proc = await asyncio.create_subprocess_exec(
        *_make_claude_cmd(),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=clean_env,
        cwd=project_root,
    )
    proc.stdin.write(input_msg.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line.decode())
            if msg.get("type") == "assistant":
                for block in msg["message"]["content"]:
                    if block.get("type") == "text":
                        yield block["text"]
        except json.JSONDecodeError:
            pass

    await proc.wait()


@app.get("/")
def dashboard():
    return FileResponse(os.path.join(_STATIC, "index.html"))


@app.get("/api/status")
def status():
    config = load_config()
    try:
        broker = AlpacaBroker(
            api_key=config["broker"]["api_key"],
            secret_key=config["broker"]["secret_key"],
            paper=config["broker"]["paper_trading"],
        )
        account = broker.get_account()
        positions = broker.get_positions()
        initial_capital = config["portfolio"].get("max_capital", account.equity)
        budget = account.equity

        risk_state = _load_risk_state()
        peak = risk_state.get("peak_equity", budget)
        drawdown = (peak - budget) / peak if peak > 0 else 0.0
        risk_cfg = config["risk"]

        return {
            "equity": round(account.equity, 2),
            "cash": round(account.cash, 2),
            "budget": round(budget, 2),
            "max_capital": initial_capital,
            "paper_trading": config["broker"]["paper_trading"],
            "positions": [
                {
                    "ticker": ticker,
                    "market_value": round(pos.market_value, 2),
                    "weight": round(pos.market_value / budget * 100, 1) if budget > 0 else 0,
                }
                for ticker, pos in sorted(positions.items())
            ],
            "risk": {
                "peak_equity": round(peak, 2),
                "current_drawdown": round(drawdown * 100, 2),
                "max_drawdown_threshold": round(risk_cfg["max_drawdown"] * 100, 1),
                "circuit_breaker_active": risk_state.get("breaker_trip_date") is not None,
            },
        }
    except Exception:
        logger.exception("Status endpoint error")
        return {"error": "Could not fetch status. Check the logs for details."}


@app.get("/api/analyze")
async def analyze():
    """SSE stream: fetch scores + macro, then stream AI analysis with web search."""

    async def stream() -> AsyncIterator[str]:
        def sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        config = load_config()
        project_root = str(Path(__file__).resolve().parent.parent.parent)

        yield sse({"type": "status", "message": "Connecting to broker..."})
        try:
            broker = AlpacaBroker(
                api_key=config["broker"]["api_key"],
                secret_key=config["broker"]["secret_key"],
                paper=config["broker"]["paper_trading"],
            )
            account = broker.get_account()
            positions = broker.get_positions()
            initial_capital = config["portfolio"].get("max_capital", account.equity)
            invested = sum(p.market_value for p in positions.values())
            budget = account.equity
        except Exception:
            logger.exception("Broker error in analyze")
            yield sse({"type": "error", "message": "Broker connection failed. Check the logs."})
            return

        yield sse({"type": "status", "message": "Fetching market data & macro indicators (15–30 sec)..."})
        loop = asyncio.get_running_loop()
        try:
            price_data, macro = await asyncio.gather(
                loop.run_in_executor(None, fetch_prices, config["etfs"], config["data"]["history_days"]),
                loop.run_in_executor(None, fetch_macro),
            )
        except Exception:
            logger.exception("Market data error in analyze")
            yield sse({"type": "error", "message": "Failed to fetch market data. Check the logs."})
            return

        if not price_data:
            yield sse({"type": "error", "message": "No market data available"})
            return

        yield sse({"type": "status", "message": "Calculating ETF scores..."})
        selected, all_etfs = rank_etfs(price_data, config)
        target_weights = compute_target_weights(selected, config["portfolio"]["sizing_method"])
        current_values = {t: p.market_value for t, p in positions.items()}
        orders = generate_orders(
            current_values, target_weights, budget, config["portfolio"]["min_trade_value"]
        )

        yield sse({
            "type": "scores",
            "equity": round(budget, 2),
            "selected": [
                {
                    "ticker": etf.ticker,
                    "composite": round(etf.composite, 3),
                    "factors": {k: round(v, 3) for k, v in etf.factors.items()},
                }
                for etf in selected
            ],
            "all_etfs": [
                {
                    "ticker": etf.ticker,
                    "composite": round(etf.composite, 3),
                    "selected": etf.ticker in {e.ticker for e in selected},
                }
                for etf in all_etfs
            ],
            "orders": [
                {"ticker": o.ticker, "side": o.side, "notional": o.notional}
                for o in orders
            ],
        })

        yield sse({"type": "status", "message": "Generating AI analysis (searching for market news)..."})
        risk_state = _load_risk_state()
        prompt = build_prompt(selected, all_etfs, orders, budget, macro, risk_state)

        try:
            async for text_chunk in _stream_claude(prompt, project_root):
                yield sse({"type": "text", "content": text_chunk})
        except Exception:
            logger.exception("AI error in analyze")
            yield sse({"type": "error", "message": "AI analysis failed. Check the logs."})
            return

        yield sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/run")
async def run_cycle():
    """SSE stream: execute the full trading cycle and stream progress."""

    async def stream() -> AsyncIterator[str]:
        def sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        config = load_config()

        yield sse({"type": "status", "message": "Connecting to broker..."})
        try:
            broker = AlpacaBroker(
                api_key=config["broker"]["api_key"],
                secret_key=config["broker"]["secret_key"],
                paper=config["broker"]["paper_trading"],
            )
            account = broker.get_account()
            positions = broker.get_positions()
            initial_capital = config["portfolio"].get("max_capital", account.equity)
            invested = sum(p.market_value for p in positions.values())
            budget = account.equity
            record_snapshot(budget, initial_capital)
        except Exception:
            logger.exception("Broker error in run")
            yield sse({"type": "error", "message": "Broker connection failed. Check the logs."})
            return

        yield sse({"type": "status", "message": f"Account ready — budget ${budget:.2f}"})

        # Circuit breaker check
        risk_cfg = config["risk"]
        monitor = DrawdownMonitor(
            max_drawdown=risk_cfg["max_drawdown"],
            cooldown_days=risk_cfg["cooldown_days"],
        )
        trading_allowed = monitor.update(budget, date.today())

        if not trading_allowed:
            yield sse({"type": "status", "message": "Circuit breaker active — liquidating all positions..."})
            broker.liquidate_all()
            yield sse({"type": "done", "orders_executed": 0, "message": "Liquidated. Holding cash."})
            return

        yield sse({"type": "status", "message": "Fetching market data (15–30 sec)..."})
        loop = asyncio.get_running_loop()
        try:
            price_data = await loop.run_in_executor(
                None, fetch_prices, config["etfs"], config["data"]["history_days"]
            )
        except Exception:
            logger.exception("Market data error in run")
            yield sse({"type": "error", "message": "Failed to fetch market data. Check the logs."})
            return

        if not price_data:
            yield sse({"type": "error", "message": "No market data available"})
            return

        yield sse({"type": "status", "message": "Scoring ETFs..."})
        selected, _ = rank_etfs(price_data, config)

        if not selected:
            yield sse({"type": "done", "orders_executed": 0, "message": "No ETFs passed scoring — holding cash."})
            return

        target_weights = compute_target_weights(selected, config["portfolio"]["sizing_method"])
        current_values = {t: p.market_value for t, p in positions.items()}
        current_weights = {t: v / budget for t, v in current_values.items()} if budget > 0 else {}

        if not needs_rebalance(current_weights, target_weights, config["portfolio"]["rebalance_threshold"]):
            yield sse({"type": "done", "orders_executed": 0, "message": "Positions within threshold — no rebalance needed."})
            return

        orders = generate_orders(
            current_values, target_weights, budget, config["portfolio"]["min_trade_value"]
        )

        sells = [o for o in orders if o.side == "sell"]
        buys = [o for o in orders if o.side == "buy"]

        yield sse({"type": "status", "message": f"Executing {len(orders)} orders..."})
        executed = 0
        for order in sells:
            try:
                result = broker.submit_order(order.ticker, order.side, order.notional, order.full_exit)
                if result:
                    executed += 1
                    yield sse({"type": "order", "ticker": order.ticker, "side": order.side, "notional": order.notional})
            except Exception:
                logger.exception(f"Order failed: {order.ticker}")
                yield sse({"type": "warning", "message": f"Order failed for {order.ticker} — check logs."})

        if buys:
            if sells:
                await asyncio.sleep(5)
            account = broker.get_account()
            available = account.buying_power * 0.99  # 1% buffer
            total_buy = sum(o.notional for o in buys)
            if total_buy > available > 0:
                scale = available / total_buy
                for o in buys:
                    o.notional = math.floor(o.notional * scale * 100) / 100

        for order in buys:
            try:
                result = broker.submit_order(order.ticker, order.side, order.notional, order.full_exit)
                if result:
                    executed += 1
                    yield sse({"type": "order", "ticker": order.ticker, "side": order.side, "notional": order.notional})
            except Exception:
                logger.exception(f"Order failed: {order.ticker}")
                yield sse({"type": "warning", "message": f"Order failed for {order.ticker} — check logs."})

        yield sse({"type": "done", "orders_executed": executed, "message": f"Trading cycle complete — {executed} orders executed."})

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/settings")
def get_settings():
    with open(_CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    config.get("broker", {}).pop("api_key", None)
    config.get("broker", {}).pop("secret_key", None)
    return config


@app.post("/api/settings")
def save_settings(body: dict):
    try:
        with open(_CONFIG_PATH) as f:
            config = yaml.safe_load(f)

        for section, allowed_fields in _SETTINGS_ALLOWED.items():
            if section not in body:
                continue
            if allowed_fields is None:
                config[section] = body[section]
            else:
                for field in allowed_fields:
                    if field in body.get(section, {}):
                        config[section][field] = body[section][field]

        with open(_CONFIG_PATH, "w") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/snapshot")
def take_snapshot():
    """Record current portfolio value without trading."""
    config = load_config()
    broker = AlpacaBroker(
        api_key=config["broker"]["api_key"],
        secret_key=config["broker"]["secret_key"],
        paper=config["broker"]["paper_trading"],
    )
    account = broker.get_account()
    initial_capital = config["portfolio"].get("max_capital", account.equity)
    budget = account.equity
    record_snapshot(budget, initial_capital)
    return {"ok": True, "portfolio_value": budget, "initial_capital": initial_capital}


@app.get("/api/portfolio-history")
def portfolio_history():
    import csv as csv_module
    path = Path("logs/portfolio_history.csv")
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        for row in csv_module.DictReader(f):
            rows.append({
                "timestamp": row["timestamp"],
                "portfolio_value": float(row["portfolio_value"]),
                "initial_capital": float(row["initial_capital"]),
            })
    return rows
