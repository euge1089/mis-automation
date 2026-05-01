from argparse import Namespace

import pytest

from pipeline import _enforce_scrape_lock


def _args(command: str, **overrides) -> Namespace:
    base = {
        "command": command,
        "with_scrape": False,
        "no_scrape": False,
    }
    base.update(overrides)
    return Namespace(**base)


def test_scrape_lock_blocks_daily_active_with_scrape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLS_SCRAPE_ENABLED", "0")
    args = _args("daily-active", with_scrape=True)
    with pytest.raises(RuntimeError, match="MLS scraping is disabled"):
        _enforce_scrape_lock(args)


def test_scrape_lock_allows_daily_active_without_scrape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLS_SCRAPE_ENABLED", "0")
    args = _args("daily-active", with_scrape=False)
    _enforce_scrape_lock(args)


def test_scrape_lock_blocks_weekly_default_scrape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLS_SCRAPE_ENABLED", "false")
    args = _args("weekly-sold-rented", no_scrape=False)
    with pytest.raises(RuntimeError, match="MLS scraping is disabled"):
        _enforce_scrape_lock(args)


def test_scrape_lock_allows_weekly_no_scrape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLS_SCRAPE_ENABLED", "false")
    args = _args("weekly-sold-rented", no_scrape=True)
    _enforce_scrape_lock(args)


def test_scrape_lock_allows_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLS_SCRAPE_ENABLED", "1")
    args = _args("monthly", with_scrape=True)
    _enforce_scrape_lock(args)
