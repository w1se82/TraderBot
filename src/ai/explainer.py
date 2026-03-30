from src.core.scorer import ScoredETF
from src.core.portfolio import Order
from src.data.market_data import MacroSnapshot


def build_prompt(
    selected: list[ScoredETF],
    all_etfs: list[ScoredETF],
    orders: list[Order],
    equity: float,
    macro: MacroSnapshot | None = None,
    risk_state: dict | None = None,
) -> str:

    # ── Selected ETFs ────────────────────────────────────────────────────────
    selected_tickers = {e.ticker for e in selected}
    etf_lines = []
    for etf in selected:
        r = etf.raw or {}
        etf_lines.append(
            f"- {etf.ticker} [SELECTED]  composite={etf.composite:.3f} | "
            f"momentum={etf.factors['momentum']:.2f} | "
            f"volatility={etf.factors['volatility']:.2f} | "
            f"trend={etf.factors['trend']:.2f} | "
            f"mean_reversion={etf.factors['mean_reversion']:.2f} | "
            f"RSI={r.get('rsi', 'n/a')} | "
            f"ann.vol={r.get('vol_pct', 'n/a')}% | "
            f"1m={r.get('return_1m', 'n/a'):+.1f}% | "
            f"3m={r.get('return_3m', 'n/a'):+.1f}% | "
            f"6m={r.get('return_6m', 'n/a'):+.1f}%"
        )

    # ── Rejected ETFs ────────────────────────────────────────────────────────
    rejected_lines = []
    for etf in all_etfs:
        if etf.ticker in selected_tickers:
            continue
        r = etf.raw or {}
        rejected_lines.append(
            f"- {etf.ticker} [rejected]   composite={etf.composite:.3f} | "
            f"momentum={etf.factors['momentum']:.2f} | "
            f"volatility={etf.factors['volatility']:.2f} | "
            f"trend={etf.factors['trend']:.2f} | "
            f"mean_reversion={etf.factors['mean_reversion']:.2f} | "
            f"RSI={r.get('rsi', 'n/a')} | "
            f"ann.vol={r.get('vol_pct', 'n/a')}% | "
            f"1m={r.get('return_1m', 'n/a'):+.1f}% | "
            f"3m={r.get('return_3m', 'n/a'):+.1f}% | "
            f"6m={r.get('return_6m', 'n/a'):+.1f}%"
        )

    # ── Orders ───────────────────────────────────────────────────────────────
    order_lines = [f"- {o.side.upper()} {o.ticker}: ${o.notional:.2f}" for o in orders]

    # ── Macro block ──────────────────────────────────────────────────────────
    if macro:
        vix_signal = "elevated fear" if macro.vix > 25 else ("low fear" if macro.vix < 15 else "neutral")
        macro_block = (
            f"\n**Macro indicators (live):**\n"
            f"- VIX: {macro.vix} ({macro.vix_1m_change:+.1f} pts past month) — {vix_signal}\n"
            f"- US 10Y yield: {macro.yield_10y}% ({macro.yield_1m_change:+.0f} bps past month)\n"
            f"- US Dollar Index (DXY): {macro.dxy}\n"
            f"- SPY 1-month return (market proxy): {macro.spy_1m_return:+.1f}%"
        )
    else:
        macro_block = "\n**Macro indicators:** unavailable"

    # ── Risk state ───────────────────────────────────────────────────────────
    if risk_state:
        peak = risk_state.get("peak_equity", equity)
        drawdown = (peak - equity) / peak * 100 if peak > 0 else 0.0
        breaker = "ACTIVE" if risk_state.get("breaker_trip_date") else "inactive"
        risk_block = (
            f"\n**Risk state:**\n"
            f"- Current drawdown: {drawdown:.1f}% from peak (${peak:.2f})\n"
            f"- Circuit breaker: {breaker}"
        )
    else:
        risk_block = ""

    all_lines = etf_lines + rejected_lines

    return f"""You are a quantitative ETF portfolio analyst with access to the WebSearch tool.
Before writing your analysis, use WebSearch to find 1–2 current news items relevant to the selected ETFs or macro environment (e.g. Fed signals, sector developments, geopolitical risk). Briefly cite what you found.

**Portfolio equity:** ${equity:.2f}
{macro_block}
{risk_block}

**Full ETF ranking (all {len(all_etfs)} scored):**
{chr(10).join(all_lines) if all_lines else "No ETFs scored"}

**Factor legend (normalised 0–1):**
- momentum: percentile rank of weighted return (1m/3m/6m) — high = strong upward trend
- volatility: inverted percentile rank — high = low volatility (defensive profile)
- trend (0/0.5/1): price vs SMA50/SMA200 — 1.0 = above both moving averages
- mean_reversion: RSI-based — high = oversold (potential buying opportunity)

**Generated orders:**
{chr(10).join(order_lines) if order_lines else "No orders — positions already balanced"}

Write a concise analysis (max 400 words) covering:
1. What the macro environment (VIX, yields, DXY) and recent news imply for risk appetite
2. Why the selected ETFs score highest versus the rejected ones — reference the raw values (RSI, vol%, returns)
3. Any risks or points of attention for the period ahead"""
