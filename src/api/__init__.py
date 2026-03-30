import asyncio
import json
import logging
import os
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from src.ai.explainer import build_prompt
from src.broker.alpaca_broker import AlpacaBroker
from src.config import load_config
from src.core.portfolio import compute_target_weights, generate_orders
from src.core.scorer import rank_etfs
from src.data.market_data import fetch_prices

app = FastAPI(title="TraderBot")
logger = logging.getLogger(__name__)

_STATIC = os.path.join(os.path.dirname(__file__), "static")


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
        max_capital = config["portfolio"].get("max_capital", account.equity)
        invested = sum(p.market_value for p in positions.values())
        budget = min(max_capital, invested + account.cash)

        risk_state: dict = {}
        state_path = "logs/risk_state.json"
        if os.path.exists(state_path):
            with open(state_path) as f:
                risk_state = json.load(f)

        peak = risk_state.get("peak_equity", budget)
        drawdown = (peak - budget) / peak if peak > 0 else 0.0
        risk_cfg = config["risk"]

        return {
            "equity": round(account.equity, 2),
            "cash": round(account.cash, 2),
            "budget": round(budget, 2),
            "max_capital": max_capital,
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
    except Exception as e:
        logger.exception("Status endpoint error")
        return {"error": str(e)}


@app.get("/api/analyze")
async def analyze():
    """SSE stream: fetches scores then streams AI explanation."""

    async def stream() -> AsyncIterator[str]:
        def sse(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        config = load_config()

        yield sse({"type": "status", "message": "Verbinding met broker..."})
        try:
            broker = AlpacaBroker(
                api_key=config["broker"]["api_key"],
                secret_key=config["broker"]["secret_key"],
                paper=config["broker"]["paper_trading"],
            )
            account = broker.get_account()
            positions = broker.get_positions()
            max_capital = config["portfolio"].get("max_capital", account.equity)
            invested = sum(p.market_value for p in positions.values())
            budget = min(max_capital, invested + account.cash)
        except Exception as e:
            yield sse({"type": "error", "message": f"Broker fout: {e}"})
            return

        yield sse({"type": "status", "message": "Marktdata ophalen (15–30 sec)..."})
        loop = asyncio.get_running_loop()
        try:
            price_data = await loop.run_in_executor(
                None, fetch_prices, config["etfs"], config["data"]["history_days"]
            )
        except Exception as e:
            yield sse({"type": "error", "message": f"Marktdata fout: {e}"})
            return

        if not price_data:
            yield sse({"type": "error", "message": "Geen marktdata beschikbaar"})
            return

        yield sse({"type": "status", "message": "ETF scores berekenen..."})
        selected = rank_etfs(price_data, config)
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
            "orders": [
                {"ticker": o.ticker, "side": o.side, "notional": o.notional}
                for o in orders
            ],
        })

        yield sse({"type": "status", "message": "AI analyse genereren..."})
        prompt = build_prompt(selected, orders, budget)

        try:
            clean_env = {k: v for k, v in os.environ.items()
                         if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE")}

            cmd = [
                "/home/w1s3guy/.local/bin/claude",
                "--output-format", "stream-json",
                "--verbose",
                "--setting-sources", "",
                "--input-format", "stream-json",
                "--max-turns", "1",
            ]

            input_msg = json.dumps({
                "type": "user",
                "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}
            }) + "\n"

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=clean_env,
                cwd="/home/w1s3guy/PycharmProjects/TraderBot",
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
                                yield sse({"type": "text", "content": block["text"]})
                except json.JSONDecodeError:
                    pass

            await proc.wait()
        except Exception as e:
            yield sse({"type": "error", "message": f"AI fout: {e}"})
            return

        yield sse({"type": "done"})

    return StreamingResponse(stream(), media_type="text/event-stream")
