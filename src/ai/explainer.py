from src.core.scorer import ScoredETF
from src.core.portfolio import Order


def build_prompt(selected: list[ScoredETF], orders: list[Order], equity: float) -> str:
    etf_lines = []
    for etf in selected:
        etf_lines.append(
            f"- {etf.ticker}: score={etf.composite:.3f} | "
            f"momentum={etf.factors['momentum']:.2f} | "
            f"volatility={etf.factors['volatility']:.2f} | "
            f"trend={etf.factors['trend']:.2f} | "
            f"mean_reversion={etf.factors['mean_reversion']:.2f}"
        )

    order_lines = []
    for order in orders:
        order_lines.append(f"- {order.side.upper()} {order.ticker}: ${order.notional:.2f}")

    return f"""You are a quantitative ETF portfolio analyst. Analyse the following trading decisions and provide professional insights.

**Portfolio equity:** ${equity:.2f}

**Selected ETFs (multi-factor scoring):**
{chr(10).join(etf_lines) if etf_lines else "No ETFs selected — holding cash position"}

**Factor legend:**
- momentum (0–1): percentile rank of weighted return (1m/3m/6m) — high = strong upward trend
- volatility (0–1): inverted percentile rank — high = low volatility (defensive profile)
- trend (0/0.5/1): position relative to SMA50 and SMA200 — 1.0 = above both moving averages
- mean_reversion (0–1): RSI-based — high = oversold (potential buying opportunity)

**Generated orders:**
{chr(10).join(order_lines) if order_lines else "No orders — positions are already balanced"}

Provide an analysis of at most 300 words. Cover:
1. What the factor combination reveals about the current market climate
2. Why these specific ETFs are of interest and what their profile indicates
3. Any risks or points of attention for the period ahead"""
