import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "risk_state.json"


class DrawdownMonitor:
    def __init__(self, max_drawdown: float = 0.15, cooldown_days: int = 5):
        self.max_drawdown = max_drawdown
        self.cooldown_days = cooldown_days
        self.peak_equity: float = 0.0
        self.breaker_tripped_date: date | None = None
        self._load_state()

    def update(self, current_equity: float, current_date: date) -> bool:
        self.peak_equity = max(self.peak_equity, current_equity)

        if self.peak_equity == 0:
            self._save_state()
            return True

        drawdown = (self.peak_equity - current_equity) / self.peak_equity

        logger.info(
            f"Equity: ${current_equity:.2f}, peak: ${self.peak_equity:.2f}, "
            f"drawdown: {drawdown:.1%}"
        )

        if drawdown >= self.max_drawdown:
            if self.breaker_tripped_date is None:
                self.breaker_tripped_date = current_date
                logger.critical(
                    f"CIRCUIT BREAKER TRIPPED: drawdown {drawdown:.1%} >= {self.max_drawdown:.0%}"
                )
            self._save_state()
            return False

        if self.breaker_tripped_date is not None:
            days_since = (current_date - self.breaker_tripped_date).days
            if days_since < self.cooldown_days:
                logger.warning(
                    f"Circuit breaker cooldown: {days_since}/{self.cooldown_days} days"
                )
                self._save_state()
                return False
            else:
                logger.info("Circuit breaker cooldown expired, resuming trading")
                self.breaker_tripped_date = None
                self.peak_equity = current_equity

        self._save_state()
        return True

    def _load_state(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text())
            self.peak_equity = data.get("peak_equity", 0.0)
            tripped = data.get("breaker_tripped_date")
            self.breaker_tripped_date = date.fromisoformat(tripped) if tripped else None
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Could not load risk state: {e}")

    def _save_state(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "peak_equity": self.peak_equity,
            "breaker_tripped_date": (
                self.breaker_tripped_date.isoformat() if self.breaker_tripped_date else None
            ),
        }
        STATE_FILE.write_text(json.dumps(data, indent=2))
