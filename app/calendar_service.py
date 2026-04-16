"""
Trading calendar for A-share market.
Holidays sourced from AKShare (tool_trade_date_hist_sina).
Falls back to a static list if AKShare is unavailable.
"""
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)

# Static fallback: 2025 A-share non-trading dates (public holidays only, weekends excluded)
_STATIC_HOLIDAYS_2025 = {
    date(2025, 1, 1),   # New Year
    date(2025, 1, 28), date(2025, 1, 29), date(2025, 1, 30),
    date(2025, 1, 31), date(2025, 2, 3), date(2025, 2, 4),  # Spring Festival
    date(2025, 4, 4),   # Qingming
    date(2025, 5, 1), date(2025, 5, 2),  # Labour Day
    date(2025, 5, 31), date(2025, 6, 2),  # Dragon Boat
    date(2025, 10, 1), date(2025, 10, 2), date(2025, 10, 3),
    date(2025, 10, 6), date(2025, 10, 7), date(2025, 10, 8),  # National Day
}


class CalendarService:
    def __init__(self):
        self._holidays: set[date] = set(_STATIC_HOLIDAYS_2025)
        self._trading_days_from_akshare: set[date] | None = None
        self._try_load_from_akshare()

    def _try_load_from_akshare(self):
        try:
            import akshare as ak
            df = ak.tool_trade_date_hist_sina()
            from datetime import datetime
            trading = set()
            for val in df["trade_date"].tolist():
                if isinstance(val, str):
                    trading.add(datetime.strptime(val, "%Y-%m-%d").date())
                else:
                    trading.add(val)
            self._trading_days_from_akshare = trading
            logger.info("Loaded trading calendar from AKShare: %d days", len(self._trading_days_from_akshare))
        except Exception as e:
            logger.warning("AKShare calendar unavailable, using static list: %s", e)

    def is_trading_day(self, d: date) -> bool:
        if d.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        if self._trading_days_from_akshare is not None:
            return d in self._trading_days_from_akshare
        return d not in self._holidays

    def next_trading_day(self, d: date) -> date:
        candidate = d + timedelta(days=1)
        while not self.is_trading_day(candidate):
            candidate += timedelta(days=1)
        return candidate
