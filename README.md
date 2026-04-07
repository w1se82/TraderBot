# TraderBot

Automated multi-factor ETF trading bot. Scores a universe of US-listed ETFs daily on three factors, selects the top performers, and rebalances via Alpaca. Idle cash is automatically swept back into holdings. Designed as a fire & forget system running on a Raspberry Pi.

## Strategy

The bot ranks ETFs based on three configurable factors. All factors are cross-sectionally percentile-ranked before scoring, so the composite is always a fair 0–1 comparison across the universe.

| Factor | Default Weight | What it measures |
|--------|---------------|-----------------|
| Momentum | 30% | Weighted average of 1m, 3m, and 6m returns |
| Volatility | 30% | Ratio of 21-day vol to 126-day vol — rewards assets calmer than their own norm |
| Trend | 40% | Distance of price above/below the 200-day SMA |

The top N ETFs (default 3) are held using score-proportional sizing. Rebalancing only occurs when a position drifts more than the configured threshold (default 8%) from its target.

A **hold protection** rule prevents replacing a position that was acquired less than `min_hold_days` (default 5) ago, avoiding daily churn when scores between ETFs are close.

### ETF Universe

Configurable via the dashboard or `settings.yaml`. Default set:

| Ticker | Description | Default |
|--------|------------|---------|
| SPY | S&P 500 | On |
| VEA | Developed Markets ex-US | On |
| VWO | Emerging Markets | On |
| TLT | US Treasuries (long-term) | On |
| GLD | Gold | On |
| IEF | US Treasuries (mid-term) | On |
| LQD | Corporate Bonds | On |
| DBC | Commodities | On |
| QQQ | Nasdaq 100 | Off |
| VTI | Total US Market | Off |

### Risk Management

- **Drawdown circuit breaker**: liquidates all positions if the portfolio drops more than the configured threshold (default 15%) from its peak
- **Cooldown**: stays in cash for N days (default 5) after a trip, then resets
- **Hold protection**: prevents replacing a position held less than `min_hold_days` (default 5), avoiding score-noise-driven churn
- **Rebalance threshold**: 8% drift before rebalancing (prevents unnecessary small trades)
- **Minimum trade value**: $25 — filters out sub-threshold rebalance noise
- **Alpaca $1 minimum**: buy orders below $1 are skipped instead of crashing
- **Cash sweep**: after rebalancing, any remaining cash (> $3) is distributed proportionally across target holdings so capital stays fully deployed
- **Buying power cap**: buy notionals are always capped to `buying_power × 0.99` before submission, preventing insufficient-funds errors regardless of whether sells preceded the buys
- **Stale sell protection**: sell orders for positions that no longer exist on Alpaca are skipped gracefully (prevents crashes on repeated runs)
- **Intraday guard**: `python main.py guard` checks the circuit breaker without trading — run hourly via cron for intraday protection
- **PDT protection**: tracks day trades and skips sells that would exceed the 3-day-trades-per-5-days limit for accounts under $25,000

### Capital Deployment

The bot uses the full account equity (positions + cash + unrealized gains) as the budget for each cycle. After rebalancing, a **cash sweep** distributes any remaining idle cash (> $3) proportionally across target holdings, so capital stays nearly fully invested at all times.

## AI Analysis

The web dashboard includes an AI-powered analysis step driven by the **Claude Code CLI** (`claude`). After scoring the ETFs and generating orders, Claude receives a rich context and streams a qualitative explanation covering:

- What the **macro environment** implies for risk appetite (VIX, 10Y yield, DXY, SPY 1-month return)
- Why the **selected ETFs score highest** versus the rejected ones, referencing raw values (RSI, annualised vol%, 1m/3m/6m returns)
- **Current news** searched live via Claude's WebSearch tool (Fed signals, sector developments, geopolitical risk)
- **Risk state** context: current drawdown and circuit breaker status
- Any risks or points of attention for the period ahead

The Claude CLI must be installed and available in `PATH`. Claude Code authenticates independently — no additional API keys are needed.

## Daily Flow

```
16:00 CET (30 min after US market open)
  1. Record portfolio snapshot
  2. Fetch 252 days of OHLCV data via yfinance
  3. Check circuit breaker (equity vs peak)
  4. Score all ETFs on 3 factors
  5. Select top N, compute target allocation
  6. Compare with current positions
  7. Check PDT limit before executing sells
  8. Generate rebalance orders
  9. Sweep remaining cash into target holdings
  10. Execute orders via Alpaca
  11. Log everything
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
#   1. run      — execute daily trading cycle
#   2. serve    — start web dashboard
#   3. status   — show portfolio status
#   4. snapshot — record portfolio value

# Or pass a command directly
python main.py run
python main.py status
python main.py snapshot
python main.py serve         # dashboard at http://localhost:8000
python main.py serve --host 0.0.0.0  # expose on network (e.g. Raspberry Pi)
```

### Commands

| Command | Description |
|---------|------------|
| `run` | Execute the full trading cycle (score, rebalance, trade) |
| `serve` | Start the web dashboard on `localhost:8000` |
| `status` | Print portfolio status and current ETF scores to the terminal |
| `snapshot` | Record current portfolio value without trading. Run daily via cron for chart data |
| `guard` | Intraday circuit breaker check — liquidates if drawdown exceeds threshold. Run hourly via cron |

### Web Dashboard

Open `http://localhost:8000` after starting `serve`. Features:

- **Account overview** — budget, cash, paper/live mode
- **Risk status** — circuit breaker state, current drawdown with progress bar, peak equity
- **Portfolio performance chart** — interactive chart with period selector (1W / 1M / 3M / 1Y / ALL), gradient fill, and detailed tooltips showing P&L per period
- **Current positions** — ticker, market value, and portfolio weight
- **AI analysis** — runs automatically on page load: scores all ETFs, fetches macro indicators, and streams an AI-powered analysis with live market news
- **Execute button** — top-right header; runs the full trading cycle and streams a live order log
- **ETF scores table** — all ETFs ranked with factor breakdowns (selected highlighted, rejected dimmed)
- **Settings panel** — configure portfolio, risk, scoring weights, ETF universe, and paper/live mode directly from the dashboard

### Portfolio Snapshots

The bot records one portfolio value snapshot per day. Multiple runs on the same day overwrite the earlier entry, so the chart always shows one data point per day.

Snapshots are recorded automatically by:
- The `run` command (at the start of each cycle)
- The web dashboard (on every status refresh)
- The `snapshot` command (standalone, useful for cron)

## Configuration

All settings are in `config/settings.yaml` and can be edited via the web dashboard:

- **ETF universe** — which ETFs the bot can select from
- **Portfolio** — max holdings, sizing method (equal weight / score proportional), rebalance threshold, min hold days
- **Scoring weights** — relative importance of each factor (should sum to 1.0)
- **Factor parameters** — momentum windows, volatility window, SMA periods
- **Risk** — max drawdown threshold, cooldown days
- **Broker** — paper/live trading toggle

API keys are stored in `.env` (never committed to git).

## Project Structure

```
TraderBot/
├── src/
│   ├── config.py              # YAML + env var loading
│   ├── core/
│   │   ├── factors.py         # Momentum, volatility, trend
│   │   ├── scorer.py          # Factor combination, ranking, raw values
│   │   ├── portfolio.py       # Position sizing, orders, daily snapshots
│   │   └── risk.py            # Drawdown circuit breaker
│   ├── data/
│   │   └── market_data.py     # yfinance wrapper + macro snapshot (VIX, yields, DXY)
│   ├── broker/
│   │   └── alpaca_broker.py   # Alpaca API wrapper + PDT protection
│   ├── ai/
│   │   └── explainer.py       # Claude prompt builder (macro + full ranking + raw values)
│   ├── api/
│   │   ├── __init__.py        # FastAPI: status, analyze (SSE), run (SSE), settings, snapshot
│   │   └── static/
│   │       └── index.html     # Web dashboard (Tailwind + Chart.js)
│   └── cli/
│       └── __init__.py        # Typer CLI with interactive menu
├── tests/                     # Unit tests (33 tests)
├── config/
│   └── settings.yaml          # All configuration
├── deploy/
│   ├── setup-pi.sh            # Automated Raspberry Pi setup (venv, systemd, cron)
│   └── DEPLOY.md              # Deployment guide
├── logs/                      # Runtime logs, trade history, portfolio snapshots, hold state
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
4. Set `broker.paper_trading: false` in `settings.yaml` (or toggle in the dashboard)
5. Use live API keys in `.env`

## Raspberry Pi Deployment

### Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Board | Raspberry Pi 4 (2GB) | Raspberry Pi 5 (4GB) |
| OS | Raspberry Pi OS Bookworm (64-bit) | Same |
| Python | 3.11+ (included on Bookworm) | Same |
| Storage | microSD 16GB | microSD 32GB+ |
| Power supply | 15W USB-C (Pi 4) | 27W USB-C (Pi 5) |
| Network | Wi-Fi or Ethernet | Ethernet (more stable) |

Optional but recommended:
- Case with passive/active cooling
- Static IP configured in your router (for dashboard access)

### Setup

An automated setup script is included in `deploy/`:

```bash
cd TraderBot/deploy
chmod +x setup-pi.sh
./setup-pi.sh
```

This installs dependencies, creates a systemd service for the dashboard (auto-start on boot), and configures cron jobs:

| Time | Days | Command | Description |
|------|------|---------|-------------|
| 16:00 CET | Mon-Fri | `run` | Daily rebalance (30 min after open) |
| every 30 min 15:00-22:00 | Mon-Fri | `guard` | Circuit breaker check |
| 22:30 CET | Mon-Fri | `snapshot` | Log portfolio value (after close) |

See `deploy/DEPLOY.md` for the full guide.

## Tech Stack

- Python 3.11+
- yfinance (market data)
- alpaca-trade-api (order execution)
- pandas / numpy (calculations)
- FastAPI + uvicorn (web dashboard)
- Tailwind CSS + Chart.js (frontend)
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
