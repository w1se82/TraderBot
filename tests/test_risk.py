from datetime import date

import pytest

from src.core.risk import DrawdownMonitor, STATE_FILE


@pytest.fixture(autouse=True)
def clean_state(tmp_path, monkeypatch):
    fake_state = tmp_path / "risk_state.json"
    monkeypatch.setattr("src.core.risk.STATE_FILE", fake_state)
    yield


class TestDrawdownMonitor:
    def test_normal_trading(self):
        mon = DrawdownMonitor(max_drawdown=0.15)
        assert mon.update(540, date(2026, 1, 1)) is True

    def test_peak_tracks_up(self):
        mon = DrawdownMonitor(max_drawdown=0.15)
        mon.update(540, date(2026, 1, 1))
        mon.update(560, date(2026, 1, 2))
        assert mon.peak_equity == 560

    def test_breaker_trips_at_threshold(self):
        mon = DrawdownMonitor(max_drawdown=0.15)
        mon.update(600, date(2026, 1, 1))
        result = mon.update(510, date(2026, 1, 2))  # exactly 15%
        assert result is False
        assert mon.breaker_tripped_date == date(2026, 1, 2)

    def test_breaker_stays_during_cooldown(self):
        mon = DrawdownMonitor(max_drawdown=0.15, cooldown_days=5)
        mon.update(600, date(2026, 1, 1))
        mon.update(500, date(2026, 1, 2))  # trip
        # Day 3 of cooldown (1 day after trip)
        assert mon.update(550, date(2026, 1, 3)) is False

    def test_breaker_resets_after_cooldown(self):
        mon = DrawdownMonitor(max_drawdown=0.15, cooldown_days=5)
        mon.update(600, date(2026, 1, 1))
        mon.update(500, date(2026, 1, 2))  # trip
        # 5 days later
        assert mon.update(520, date(2026, 1, 7)) is True
        assert mon.breaker_tripped_date is None
        assert mon.peak_equity == 520  # reset to current

    def test_state_persists(self, tmp_path, monkeypatch):
        fake_state = tmp_path / "risk_state.json"
        monkeypatch.setattr("src.core.risk.STATE_FILE", fake_state)

        mon1 = DrawdownMonitor(max_drawdown=0.15)
        mon1.update(600, date(2026, 1, 1))

        mon2 = DrawdownMonitor(max_drawdown=0.15)
        assert mon2.peak_equity == 600
