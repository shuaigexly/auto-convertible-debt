from datetime import date
from unittest.mock import patch, MagicMock
import pytest
from app.calendar_service import CalendarService


def _make_svc_no_akshare():
    """CalendarService with AKShare disabled — uses static fallback only."""
    with patch("app.calendar_service.CalendarService._try_load_from_akshare"):
        return CalendarService()


def test_weekend_is_not_trading_day():
    svc = _make_svc_no_akshare()
    saturday = date(2025, 4, 19)
    assert not svc.is_trading_day(saturday)


def test_known_holiday_is_not_trading_day():
    svc = _make_svc_no_akshare()
    # 2025 Labour Day holiday
    assert not svc.is_trading_day(date(2025, 5, 1))


def test_regular_weekday_is_trading_day():
    svc = _make_svc_no_akshare()
    # 2025-04-16 is a Wednesday, not a holiday
    assert svc.is_trading_day(date(2025, 4, 16))


def test_next_trading_day_skips_weekend():
    svc = _make_svc_no_akshare()
    friday = date(2025, 4, 18)
    nxt = svc.next_trading_day(friday)
    assert nxt == date(2025, 4, 21)  # Monday


def test_akshare_trading_days_used_when_loaded():
    """When AKShare data is available, is_trading_day uses it instead of static list."""
    svc = _make_svc_no_akshare()
    # Inject a controlled set of trading days
    svc._trading_days_from_akshare = {date(2025, 4, 16), date(2025, 4, 17)}
    assert svc.is_trading_day(date(2025, 4, 16))
    assert not svc.is_trading_day(date(2025, 4, 15))  # Tuesday but not in set


def test_akshare_pandas_timestamp_normalized():
    """Pandas Timestamps returned by AKShare are normalized to date objects."""
    import types
    fake_ts = types.SimpleNamespace(date=lambda: date(2025, 4, 16))
    import pandas as pd
    real_ts = pd.Timestamp("2025-04-16")

    svc = _make_svc_no_akshare()

    fake_df = MagicMock()
    fake_df.__getitem__.return_value.tolist.return_value = [real_ts]

    with patch("akshare.tool_trade_date_hist_sina", return_value=fake_df):
        svc._try_load_from_akshare()

    assert svc._trading_days_from_akshare == {date(2025, 4, 16)}
    assert svc.is_trading_day(date(2025, 4, 16))
