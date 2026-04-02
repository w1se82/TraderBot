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
- **PDT protection**: tracks day trades (buy + sell same ticker same day) and skips sells that would exceed the 3-day-trades-per-5-days limit for accounts under $25,000

## AI Analysis

The web dashboard includes an AI-powered analysis step driven by the **Claude Code CLI** (`claude`). After scoring the ETFs and generating orders, Claude receives a rich context and streams a qualitative explanation covering:

- What the **macro environment** implies for risk appetite (VIX, 10Y yield, DXY, SPY 1-month return)
- Why the **selected ETFs score highest** versus the rejected ones, referencing raw values (RSI, annualised vol%, 1m/3m/6m returns)
- **Current news** searched live via Claude's WebSearch tool (Fed signals, sector developments, geopolitical risk)
- **Risk state** context: current drawdown and circuit breaker status
- Any risks or points of attention for the period ahead

The full ranking of all ETFs (selected and rejected) is passed to the prompt so Claude can explain the relative comparison explicitly.

The Claude CLI must be installed and available in `PATH`. Claude Code authenticates independently — no additional API keys are needed.

## Daily Flow

```
15:45 CET (15 min after US market open)
  1. Fetch 252 days of OHLCV data via yfinance
  2. Check circuit breaker (equity vs peak)
  3. Score all ETFs on 4 factors
  4. Select top 3, compute target allocation
  5. Compare with current positions
  6. Check PDT limit before executing sells
  7. Generate and execute orders via Alpaca
  8. Log everything
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
# Interactive menu
python main.py
#   1. run    — execute daily trading cycle
#   2. serve  — start web dashboard
#   3. status — show portfolio status

# Or pass a command directly
python main.py run
python main.py status
python main.py serve    # dashboard at http://localhost:8000
```

### Web Dashboard

Open `http://localhost:8000` after starting `serve`. The dashboard offers two actions:

- **Run Analysis** — scores all ETFs, fetches macro indicators, and streams an AI-powered analysis with live market news. Does **not** execute trades.
- **Execute Trading Cycle** — runs the full cycle (circuit breaker check → scoring → rebalance → order execution) and streams a live order feed. Confirms before proceeding.

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
│   │   ├── scorer.py          # Factor combination, ranking, raw values
│   │   ├── portfolio.py       # Position sizing and orders
│   │   └── risk.py            # Drawdown circuit breaker
│   ├── data/
│   │   └── market_data.py     # yfinance wrapper + macro snapshot (VIX, yields, DXY)
│   ├── broker/
│   │   └── alpaca_broker.py   # Alpaca API wrapper + PDT protection
│   ├── ai/
│   │   └── explainer.py       # Claude prompt builder (macro + full ranking + raw values)
│   ├── api/
│   │   ├── __init__.py        # FastAPI: status, analyze (SSE), run (SSE)
│   │   └── static/
│   │       └── index.html     # Web dashboard
│   └── cli/
│       └── __init__.py        # Typer CLI with interactive menu
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
- FastAPI + uvicorn (web dashboard)
- Claude Code CLI (AI analysis, streamed via SSE)
- typer (CLI)

## Disclaimer

This software is provided for **educational and informational purposes only**. It is not intended as financial advice, investment advice, or a recommendation to buy or sell any securities.

**Use at your own risk.** Trading stocks and ETFs involves significant risk of loss, including the potential loss of your entire investment. Past performance — whether simulated, backtested, or live — is not indicative of future results.

The authors and contributors of this project:
- Are not licensed financial advisors, brokers, or dealers
- Make no guarantees about the accuracy, reliability, or completeness of the trading strategy
- Accept no liability for any financial losses incurred through the use of this software
- Do not guarantee that the circuit breaker or any risk management feature will prevent losses in all market conditions

Before trading with real money, you should:
- Understand the risks involved in algorithmic trading
- Consult with a qualified financial advisor
- Only invest money you can afford to lose
- Thoroughly test the strategy using paper trading

By using this software, you acknowledge that you are solely responsible for any trading decisions and their outcomes.
