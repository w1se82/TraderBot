import pytest

from src.core.portfolio import Order, compute_target_weights, generate_orders, needs_rebalance
from src.core.scorer import ScoredETF


def _etf(ticker: str) -> ScoredETF:
    return ScoredETF(ticker=ticker, composite=0.5, factors={})


class TestComputeTargetWeights:
    def test_equal_weight_3(self):
        weights = compute_target_weights([_etf("A"), _etf("B"), _etf("C")])
        assert len(weights) == 3
        assert all(abs(w - 1 / 3) < 1e-9 for w in weights.values())

    def test_empty(self):
        assert compute_target_weights([]) == {}


class TestNeedsRebalance:
    def test_within_threshold(self):
        current = {"SPY": 0.33, "QQQ": 0.34, "GLD": 0.33}
        target = {"SPY": 0.333, "QQQ": 0.333, "GLD": 0.333}
        assert not needs_rebalance(current, target, 0.05)

    def test_exceeds_threshold(self):
        current = {"SPY": 0.50, "QQQ": 0.50}
        target = {"SPY": 0.333, "QQQ": 0.333, "GLD": 0.333}
        assert needs_rebalance(current, target, 0.05)

    def test_new_position(self):
        current = {"SPY": 0.50, "QQQ": 0.50}
        target = {"SPY": 0.50, "QQQ": 0.25, "GLD": 0.25}
        assert needs_rebalance(current, target, 0.05)


class TestGenerateOrders:
    def test_sells_before_buys(self):
        current = {"SPY": 300, "QQQ": 300}
        target = {"QQQ": 0.5, "GLD": 0.5}
        orders = generate_orders(current, target, 600, min_trade_value=1.0)

        sell_idx = [i for i, o in enumerate(orders) if o.side == "sell"]
        buy_idx = [i for i, o in enumerate(orders) if o.side == "buy"]
        if sell_idx and buy_idx:
            assert max(sell_idx) < min(buy_idx)

    def test_skips_small_trades(self):
        current = {"SPY": 180}
        target = {"SPY": 1.0}
        orders = generate_orders(current, target, 180.5, min_trade_value=1.0)
        assert len(orders) == 0

    def test_full_sell_and_buy(self):
        current = {"OLD": 500}
        target = {"NEW": 1.0}
        orders = generate_orders(current, target, 500, min_trade_value=1.0)
        assert len(orders) == 2
        assert orders[0].side == "sell"
        assert orders[0].ticker == "OLD"
        assert orders[1].side == "buy"
        assert orders[1].ticker == "NEW"
