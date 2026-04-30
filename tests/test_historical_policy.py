"""Tests for rolling weekly window helpers."""

from datetime import date

from historical_policy import rolling_three_month_window, subtract_calendar_months


def test_subtract_calendar_months_same_day_when_valid() -> None:
    d = date(2026, 4, 29)
    assert subtract_calendar_months(d, 3) == date(2026, 1, 29)


def test_subtract_calendar_months_clamps_day_to_month_end() -> None:
    # March 31 minus 1 month -> February (clamp to 28/29)
    assert subtract_calendar_months(date(2026, 3, 31), 1) == date(2026, 2, 28)


def test_rolling_three_month_window_end_is_today() -> None:
    as_of = date(2026, 6, 15)
    w = rolling_three_month_window(as_of)
    assert w.end == as_of
    assert w.start == subtract_calendar_months(as_of, 3)
