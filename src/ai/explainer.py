from src.core.scorer import ScoredETF
from src.core.portfolio import Order


def build_prompt(selected: list[ScoredETF], orders: list[Order], equity: float) -> str:
    etf_lines = []
    for etf in selected:
        etf_lines.append(
            f"- {etf.ticker}: score={etf.composite:.3f} | "
            f"momentum={etf.factors['momentum']:.2f} | "
            f"volatiliteit={etf.factors['volatility']:.2f} | "
            f"trend={etf.factors['trend']:.2f} | "
            f"mean_reversion={etf.factors['mean_reversion']:.2f}"
        )

    order_lines = []
    for order in orders:
        order_lines.append(f"- {order.side.upper()} {order.ticker}: ${order.notional:.2f}")

    return f"""Je bent een kwantitatieve ETF portfolio analist. Analyseer de volgende trading beslissingen en geef professioneel advies in het Nederlands.

**Portfolio equity:** ${equity:.2f}

**Geselecteerde ETFs (multi-factor scoring):**
{chr(10).join(etf_lines) if etf_lines else "Geen ETFs geselecteerd — cash positie aangehouden"}

**Factor legenda:**
- momentum (0–1): percentiel rank van gewogen rendement (1m/3m/6m) — hoog = sterke opwaartse trend
- volatiliteit (0–1): inverted percentiel rank — hoog = lage volatiliteit (defensief profiel)
- trend (0/0.5/1): positie t.o.v. SMA50 en SMA200 — 1.0 = boven beide gemiddelden
- mean_reversion (0–1): RSI-gebaseerd — hoog = oversold (potentiële koopkans)

**Gegenereerde orders:**
{chr(10).join(order_lines) if order_lines else "Geen orders — posities zijn al in balans"}

Geef een analyse van maximaal 300 woorden. Bespreek:
1. Wat de factor-combinatie onthult over het huidige marktklimaat
2. Waarom deze specifieke ETFs interessant zijn en wat hun profiel vertelt
3. Eventuele risico's of aandachtspunten voor de komende periode"""
