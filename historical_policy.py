from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date


def _as_date(value: date | datetime | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    return value


def first_day_of_month(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    first = first_day_of_month(d)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return next_month - timedelta(days=1)


def add_months(d: date, months: int) -> date:
    year = d.year + ((d.month - 1 + months) // 12)
    month = ((d.month - 1 + months) % 12) + 1
    return date(year, month, 1)


def memorialize_through(as_of: date | datetime | None = None) -> date:
    """
    End-of-month cutoff based on first day of current month minus 3 months.

    Example:
    - as_of=2026-04-29 -> 2025-12-31
    """
    today = _as_date(as_of)
    current_month_start = first_day_of_month(today)
    anchor = add_months(current_month_start, -3)
    return month_end(anchor)


def hot_window(as_of: date | datetime | None = None) -> DateWindow:
    """
    Rolling re-scrape window:
      (memorialize_through + 1 day) .. as_of
    """
    today = _as_date(as_of)
    cutoff = memorialize_through(today)
    return DateWindow(start=cutoff + timedelta(days=1), end=today)


def backfill_window(
    years: int = 5,
    as_of: date | datetime | None = None,
) -> DateWindow:
    """
    Historical backfill span:
      first day of month, N years ago .. memorialize_through(as_of)
    """
    today = _as_date(as_of)
    start = date(today.year - years, 1, 1)
    end = memorialize_through(today)
    return DateWindow(start=start, end=end)


def iter_month_windows(start: date, end: date) -> list[DateWindow]:
    if end < start:
        return []
    cur = first_day_of_month(start)
    windows: list[DateWindow] = []
    while cur <= end:
        cur_end = month_end(cur)
        win_start = max(cur, start)
        win_end = min(cur_end, end)
        windows.append(DateWindow(win_start, win_end))
        cur = add_months(cur, 1)
    return windows


def to_mls_timeframe(window: DateWindow) -> str:
    """
    MLS timeframe textbox format accepted by current scrapers.
    """
    return f"{window.start:%m/%d/%Y} - {window.end:%m/%d/%Y}"
