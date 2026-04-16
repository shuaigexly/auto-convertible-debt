from datetime import date
import pytest
from app.calendar_service import CalendarService


def test_weekend_is_not_trading_day():
    svc = CalendarService()
    saturday = date(2025, 4, 19)
    assert not svc.is_trading_day(saturday)


def test_known_holiday_is_not_trading_day():
    svc = CalendarService()
    # 2025 Labour Day holiday
    assert not svc.is_trading_day(date(2025, 5, 1))


def test_regular_weekday_is_trading_day():
    svc = CalendarService()
    # 2025-04-16 is a Wednesday, not a holiday
    assert svc.is_trading_day(date(2025, 4, 16))


def test_next_trading_day_skips_weekend():
    svc = CalendarService()
    friday = date(2025, 4, 18)
    nxt = svc.next_trading_day(friday)
    assert nxt == date(2025, 4, 21)  # Monday
