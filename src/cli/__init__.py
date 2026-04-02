import json
import logging
import math
from datetime import date
from pathlib import Path

import typer

from src.broker.alpaca_broker import AlpacaBroker
from src.config import load_config, setup_logging
from src.core.portfolio import compute_target_weights, generate_orders, needs_rebalance, record_snapshot
from src.core.risk import DrawdownMonitor
from src.core.scorer import ScoredETF, rank_etfs
from src.data.market_data import fetch_prices

app = typer.Typer(name="traderbot", help="ETF Trading Bot", invoke_without_command=True)
logger = logging.getLogger(__name__)

_HOLD_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "hold_state.json"


def _load_hold_state() -> dict[str, str]:
    """Return {ticker: iso_date} recording when each position was last acquired."""
    if not _HOLD_STATE_FILE.exists():
        return {}
    try:
        return json.loads(_HOLD_STATE_FILE.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def _save_hold_state(holdings_since: dict[str, str]) -> None:
    _HOLD_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HOLD_STATE_FILE.write_text(json.dumps(holdings_since, indent=2))


def _apply_hold_protection(
    selected: list[ScoredETF],
    all_ranked: list[ScoredETF],
    current_tickers: set[str],
    holdings_since: dict[str, str],
    min_hold_days: int,
    max_holdings: int,
    today: date,
) -> list[ScoredETF]:
    """Prevent replacing a holding that hasn't been held for min_hold_days yet."""
    protected = {
        t for t in current_tickers
        if t in holdings_since
        and (today - date.fromisoformat(holdings_since[t])).days < min_hold_days
    }
    selected_tickers = {e.ticker for e in selected}
    dropped = protected - selected_tickers

    if not dropped:
        return selected

    result = list(selected)
    ranked_by_ticker = {e.ticker: e for e in all_ranked}
    for ticker in dropped:
        if ticker in ranked_by_ticker:
            logger.info(f"Hold protection: retaining {ticker} (held < {min_hold_days} days)")
            result.append(ranked_by_ticker[ticker])

    # Trim to max_holdings by evicting lowest-scoring unprotected newcomers
    while len(result) > max_holdings:
        evictable = [e for e in result if e.ticker not in protected]
        if not evictable:
            break
        worst = min(evictable, key=lambda e: e.composite)
        result.remove(worst)

    return result


@app.callback()
def main(ctx: typer.Context):
    """ETF Trading Bot — interactive menu when run without arguments."""
    if ctx.invoked_subcommand is not None:
        return

    typer.echo("\n  TraderBot")
    typer.echo("  " + "─" * 20)
    typer.echo("  1. run      — execute daily trading cycle")
    typer.echo("  2. serve    — start web dashboard")
    typer.echo("  3. status   — show portfolio status")
    typer.echo("  4. snapshot — record portfolio value")
    typer.echo("  5. guard    — intraday circuit breaker check")
    typer.echo()

    choice = typer.prompt("  Choose [1/2/3/4/5]").strip()

    if choice in ("1", "run"):
        ctx.invoke(run)
    elif choice in ("2", "serve"):
        ctx.invoke(serve)
    elif choice in ("3", "status"):
        ctx.invoke(status)
    elif choice in ("4", "snapshot"):
        ctx.invoke(snapshot)
    elif choice in ("5", "guard"):
        ctx.invoke(guard)
    else:
        typer.echo("Invalid choice.", err=True)
        raise typer.Exit(1)


@app.command()
def run():
    """Run the daily trading cycle."""
    config = load_config()
    setup_logging(config)
    logger.info("=== TraderBot daily run ===")

    try:
        _run_cycle(config)
    except Exception:
        logger.exception("Fatal error in trading cycle")
        raise typer.Exit(1)


def _run_cycle(config: dict) -> None:
    # 1. Connect to broker
    broker = AlpacaBroker(
        api_key=config["broker"]["api_key"],
        secret_key=config["broker"]["secret_key"],
        paper=config["broker"]["paper_trading"],
    )

    # 2. Get account info and apply capital limit
    account = broker.get_account()
    initial_capital = config["portfolio"].get("max_capital", account.equity)
    positions = broker.get_positions()
    budget = account.equity
    logger.info(
        f"Account equity: ${account.equity:.2f}, "
        f"budget: ${budget:.2f} (initial: ${initial_capital:.2f})"
    )
    record_snapshot(budget, initial_capital)

    # 3. Check circuit breaker
    risk_cfg = config["risk"]
    monitor = DrawdownMonitor(
        max_drawdown=risk_cfg["max_drawdown"],
        cooldown_days=risk_cfg["cooldown_days"],
    )
    today = date.today()
    trading_allowed = monitor.update(budget, today)

    if not trading_allowed:
        logger.warning("Circuit breaker active — liquidating all positions")
        broker.liquidate_all()
        _save_hold_state({})
        return

    # 4. Fetch market data
    price_data = fetch_prices(config["etfs"], config["data"]["history_days"])
    if not price_data:
        logger.error("No market data available, aborting")
        return

    # 5. Score and rank ETFs
    selected, all_ranked = rank_etfs(price_data, config)
    if not selected:
        logger.warning("No ETFs passed scoring, holding cash")
        return

    # 6. Apply hold protection to prevent daily churn
    holdings_since = _load_hold_state()
    min_hold_days = config["portfolio"].get("min_hold_days", 5)
    selected = _apply_hold_protection(
        selected, all_ranked, set(positions.keys()),
        holdings_since, min_hold_days,
        config["portfolio"]["max_holdings"], today,
    )

    # 7. Compute target weights
    target_weights = compute_target_weights(
        selected, config["portfolio"]["sizing_method"]
    )

    # 8. Compute current weights based on budget
    current_values = {t: p.market_value for t, p in positions.items()}
    current_weights = {t: v / budget for t, v in current_values.items()} if budget > 0 else {}

    # 9. Check rebalance threshold
    if not needs_rebalance(current_weights, target_weights, config["portfolio"]["rebalance_threshold"]):
        logger.info("Positions within threshold, no rebalance needed")
        return

    # 10. Generate and execute orders
    orders = generate_orders(
        current_values, target_weights, budget, config["portfolio"]["min_trade_value"]
    )

    import time
    sells = [o for o in orders if o.side == "sell"]
    buys = [o for o in orders if o.side == "buy"]
    for order in sells:
        broker.submit_order(order.ticker, order.side, order.notional, order.full_exit)
    if buys:
        if sells:
            time.sleep(5)
        account = broker.get_account()
        available = account.buying_power * 0.99  # 1% buffer
        total_buy = sum(o.notional for o in buys)
        if total_buy > available > 0:
            scale = available / total_buy
            for o in buys:
                o.notional = math.floor(o.notional * scale * 100) / 100
    for order in buys:
        broker.submit_order(order.ticker, order.side, order.notional, order.full_exit)

    # 11. Update hold state: register new buys, remove full exits
    for order in buys:
        holdings_since[order.ticker] = today.isoformat()
    for order in sells:
        if order.full_exit:
            holdings_since.pop(order.ticker, None)
    _save_hold_state(holdings_since)

    logger.info(f"Executed {len(orders)} orders")
    logger.info("=== Daily run complete ===")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Start the web dashboard."""
    import uvicorn
    config = load_config()
    setup_logging(config)
    logger.info(f"Starting dashboard on http://{host}:{port}")
    uvicorn.run("src.api:app", host=host, port=port, reload=False)


@app.command()
def snapshot():
    """Record current portfolio value (no trades). Run daily via cron."""
    config = load_config()
    setup_logging(config)

    broker = AlpacaBroker(
        api_key=config["broker"]["api_key"],
        secret_key=config["broker"]["secret_key"],
        paper=config["broker"]["paper_trading"],
    )

    account = broker.get_account()
    initial_capital = config["portfolio"].get("max_capital", account.equity)
    budget = account.equity

    record_snapshot(budget, initial_capital)
    typer.echo(f"Snapshot recorded: ${budget:.2f} (initial: ${initial_capital:.2f})")


@app.command()
def status():
    """Show current portfolio status and scores."""
    config = load_config()
    setup_logging(config)

    broker = AlpacaBroker(
        api_key=config["broker"]["api_key"],
        secret_key=config["broker"]["secret_key"],
        paper=config["broker"]["paper_trading"],
    )

    account = broker.get_account()
    positions = broker.get_positions()
    budget = account.equity

    invested = sum(p.market_value for p in positions.values())

    typer.echo(f"\n{'=' * 50}")
    typer.echo(f"  Account: {'PAPER' if config['broker']['paper_trading'] else 'LIVE'}")
    typer.echo(f"  Equity:  ${budget:.2f}")
    typer.echo(f"  Invested: ${invested:.2f}")
    typer.echo(f"  Cash:    ${account.cash:.2f}")
    typer.echo(f"{'=' * 50}")

    if positions:
        typer.echo(f"\n  {'Ticker':<8} {'Value':>10} {'Weight':>8}")
        typer.echo(f"  {'-' * 28}")
        for ticker, pos in sorted(positions.items()):
            weight = pos.market_value / budget * 100 if budget else 0
            typer.echo(f"  {ticker:<8} ${pos.market_value:>9.2f} {weight:>7.1f}%")
    else:
        typer.echo("\n  No open positions")

    # Show current scores
    typer.echo(f"\n  Current ETF scores:")
    typer.echo(f"  {'-' * 40}")
    price_data = fetch_prices(config["etfs"], config["data"]["history_days"])
    if price_data:
        selected, _ = rank_etfs(price_data, config)
        for etf in selected:
            typer.echo(f"  {etf.ticker:<6} composite={etf.composite:.3f}")

    typer.echo()


@app.command()
def guard():
    """Intraday circuit breaker check — liquidates if drawdown exceeds threshold.

    Run hourly via cron during market hours (e.g. every hour 15:00–22:00 CET Mon-Fri).
    Does not rebalance — only protects against large intraday moves.
    """
    config = load_config()
    setup_logging(config)

    broker = AlpacaBroker(
        api_key=config["broker"]["api_key"],
        secret_key=config["broker"]["secret_key"],
        paper=config["broker"]["paper_trading"],
    )

    account = broker.get_account()
    risk_cfg = config["risk"]
    monitor = DrawdownMonitor(
        max_drawdown=risk_cfg["max_drawdown"],
        cooldown_days=risk_cfg["cooldown_days"],
    )
    trading_allowed = monitor.update(account.equity, date.today())

    if not trading_allowed:
        logger.critical(
            f"GUARD: circuit breaker tripped at ${account.equity:.2f} — liquidating all positions"
        )
        broker.liquidate_all()
        _save_hold_state({})
        typer.echo(f"Circuit breaker tripped — liquidated all positions (equity ${account.equity:.2f})")
    else:
        logger.info(f"GUARD: equity ${account.equity:.2f} — no action needed")
