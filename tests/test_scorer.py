from src.core.scorer import ScoredETF, _percentile_rank, rank_etfs


SAMPLE_CONFIG = {
    "factors": {
        "momentum": {"windows": [21, 63, 126], "weights": [0.33, 0.33, 0.34]},
        "volatility": {"window": 63},
        "trend": {"sma_short": 50, "sma_long": 200},
    },
    "scoring": {
        "momentum_weight": 0.40,
        "volatility_weight": 0.30,
        "trend_weight": 0.30,
    },
    "portfolio": {"max_holdings": 2},
}


class TestPercentileRank:
    def test_basic(self):
        ranks = _percentile_rank([10, 20, 30])
        assert ranks[0] < ranks[1] < ranks[2]

    def test_all_equal(self):
        ranks = _percentile_rank([5, 5, 5])
        assert all(r == ranks[0] for r in ranks)

    def test_single_value(self):
        ranks = _percentile_rank([42])
        assert ranks == [0.5]


class TestRankETFs:
    def test_returns_max_holdings(self, sample_universe):
        selected, _ = rank_etfs(sample_universe, SAMPLE_CONFIG)
        assert len(selected) == 2

    def test_returns_scored_etfs(self, sample_universe):
        selected, _ = rank_etfs(sample_universe, SAMPLE_CONFIG)
        for etf in selected:
            assert isinstance(etf, ScoredETF)
            assert 0 <= etf.composite <= 1

    def test_sorted_descending(self, sample_universe):
        selected, _ = rank_etfs(sample_universe, SAMPLE_CONFIG)
        assert selected[0].composite >= selected[1].composite

    def test_uptrend_beats_downtrend(self, sample_universe):
        config = {**SAMPLE_CONFIG, "portfolio": {"max_holdings": 5}}
        selected, _ = rank_etfs(sample_universe, config)
        tickers = [r.ticker for r in selected]
        assert tickers.index("UP") < tickers.index("DOWN")
