# TraderBot

Automated multi-factor ETF trading bot. Scores a universe of US-listed ETFs daily on four factors, selects the top 3, and rebalances via Alpaca. Designed as a fire & forget system running on a Raspberry Pi.

## Strategy

The bot ranks ETFs based on four factors:

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Momentum | 35% | Weighted average of 1m, 3m, and 6m returns |
| Volatility | 25% | 3-month annualized vol (lower = better) |
| Trend | 25% | Price vs SMA50/SMA200 |
| Mean Reversion | 15% | RSI(14) — buy signal when oversold |

The top 3 ETFs are held in equal weight (~33% per position). Rebalancing only occurs when a position drifts more than 5% from its target.

### ETF Universe

| Ticker | Description |
|--------|------------|
| SPY | S&P 500 |
| QQQ | Nasdaq 100 |
| VTI | Total US Market |
| VEA | Developed Markets ex-US |
| VWO | Emerging Markets |
| TLT | US Treasuries (long-term) |
| GLD | Gold |

### Risk Management

- **Drawdown circuit breaker**: liquidates all positions if the portfolio drops more than 15% from its peak
- **Cooldown**: stays in cash for 5 days after a trip, then resets
- **Rebalance threshold**: prevents unnecessary small trades

## Daily Flow

```
22:15 CET (after US market close)
  1. Fetch 252 days of OHLCV data via yfinance
  2. Check circuit breaker (equity vs peak)
  3. Score all ETFs on 4 factors
  4. Select top 3, compute target allocation
  5. Compare with current positions
  6. Generate and execute orders via Alpaca
  7. Log everything
```

## Installation

```bash
# Clone and setup
git clone <repo-url>
cd TraderBot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Fill in your Alpaca API keys in .env
```

## Usage

```bash
# Daily trading cycle
python main.py run

# View current positions and scores
python main.py status
```

## Configuration

All settings are in `config/settings.yaml`:
- ETF universe
- Factor parameters (windows, weights)
- Portfolio settings (max holdings, rebalance threshold)
- Risk management (max drawdown, cooldown)
- Broker (paper/live toggle)

API keys are stored in `.env` (never committed to git).

## Project Structure

```
TraderBot/
├── src/
│   ├── config.py              # YAML + env var loading
│   ├── core/
│   │   ├── factors.py         # Momentum, vol, trend, RSI
│   │   ├── scorer.py          # Factor combination and ranking
│   │   ├── portfolio.py       # Position sizing and orders
│   │   └── risk.py            # Drawdown circuit breaker
│   ├── data/
│   │   └── market_data.py     # yfinance wrapper
│   ├── broker/
│   │   └── alpaca_broker.py   # Alpaca API wrapper
│   └── cli/
│       └── __init__.py        # Typer CLI (run, status)
├── tests/                     # Unit tests (35 tests)
├── config/
│   └── settings.yaml          # All configuration
├── logs/                      # Runtime logs and trade history
├── .env                       # API keys (not in git)
├── requirements.txt
└── main.py                    # Entry point
```

## Tests

```bash
pytest tests/ -v
```

All tests run on synthetic data — no API keys or network access needed.

## Paper Trading to Live

1. Run at least 60 trading days on paper trading
2. Review the trade log in `logs/trades.csv`
3. Test the circuit breaker
4. Set `broker.paper_trading: false` in `settings.yaml`
5. Use live API keys in `.env`

## Raspberry Pi Deployment

```bash
# Cron job (22:15 CET, Mon-Fri)
crontab -e
15 22 * * 1-5 cd /home/pi/TraderBot && .venv/bin/python main.py run >> logs/cron.log 2>&1
```

## Tech Stack

- Python 3.11+
- yfinance (market data)
- alpaca-trade-api (order execution)
- pandas / numpy (calculations)
- typer (CLI)
- FastAPI (dashboard, planned)
