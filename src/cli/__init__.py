import logging

import typer

from src.broker.alpaca_broker import AlpacaBroker
from src.config import load_config, setup_logging
from src.core.portfolio import compute_target_weights, generate_orders, needs_rebalance
from src.core.risk import DrawdownMonitor
from src.core.scorer import rank_etfs
from src.data.market_data import fetch_prices

app = typer.Typer(name="traderbot", help="ETF Trading Bot")
logger = logging.getLogger(__name__)


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
    max_capital = config["portfolio"].get("max_capital", account.equity)
    positions = broker.get_positions()
    invested = sum(p.market_value for p in positions.values())
    budget = min(max_capital, invested + account.cash)
    logger.info(
        f"Account equity: ${account.equity:.2f}, "
        f"budget: ${budget:.2f} (max: ${max_capital:.2f})"
    )

    # 3. Check circuit breaker
    from datetime import date
    risk_cfg = config["risk"]
    monitor = DrawdownMonitor(
        max_drawdown=risk_cfg["max_drawdown"],
        cooldown_days=risk_cfg["cooldown_days"],
    )
    trading_allowed = monitor.update(budget, date.today())

    if not trading_allowed:
        logger.warning("Circuit breaker active — liquidating all positions")
        broker.liquidate_all()
        return

    # 4. Fetch market data
    price_data = fetch_prices(config["etfs"], config["data"]["history_days"])
    if not price_data:
        logger.error("No market data available, aborting")
        return

    # 5. Score and rank ETFs
    selected = rank_etfs(price_data, config)
    if not selected:
        logger.warning("No ETFs passed scoring, holding cash")
        return

    # 6. Compute target weights
    target_weights = compute_target_weights(
        selected, config["portfolio"]["sizing_method"]
    )

    # 7. Compute current weights based on budget
    current_values = {t: p.market_value for t, p in positions.items()}
    current_weights = {t: v / budget for t, v in current_values.items()} if budget > 0 else {}

    # 8. Check rebalance threshold
    if not needs_rebalance(current_weights, target_weights, config["portfolio"]["rebalance_threshold"]):
        logger.info("Positions within threshold, no rebalance needed")
        return

    # 9. Generate and execute orders
    orders = generate_orders(
        current_values, target_weights, budget, config["portfolio"]["min_trade_value"]
    )

    for order in orders:
        broker.submit_order(order.ticker, order.side, order.notional)

    logger.info(f"Executed {len(orders)} orders")
    logger.info("=== Daily run complete ===")


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """Start the web dashboard."""
    import uvicorn
    config = load_config()
    setup_logging(config)
    logger.info(f"Starting dashboard on http://{host}:{port}")
    uvicorn.run("src.api:app", host=host, port=port, reload=False)


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
    max_capital = config["portfolio"].get("max_capital", account.equity)
    invested = sum(p.market_value for p in positions.values())
    budget = min(max_capital, invested + account.cash)

    typer.echo(f"\n{'=' * 50}")
    typer.echo(f"  Account: {'PAPER' if config['broker']['paper_trading'] else 'LIVE'}")
    typer.echo(f"  Budget:  ${budget:.2f} (max: ${max_capital:.2f})")
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
        selected = rank_etfs(price_data, config)
        for etf in selected:
            typer.echo(f"  {etf.ticker:<6} composite={etf.composite:.3f}")

    typer.echo()
