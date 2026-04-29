"""
Read MLS search-page listing count from the Results button label (e.g. "4,272 Results").

Avoids navigating to the results grid just to learn the count. Tries reading the button
as soon as it updates after a price change; only clicks Refresh Count if needed.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable

from playwright.sync_api import Page


def parse_results_button_text(txt: str) -> int | None:
    txt_clean = " ".join(txt.split())
    if not txt_clean or "result" not in txt_clean.lower():
        return None
    m = re.search(r"([\d,]+)\s*result", txt_clean, re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def try_read_results_count(page: Page) -> int | None:
    """Scan buttons whose text mentions 'result' and parse a listing count."""
    try:
        loc = page.locator("button").filter(has_text=re.compile(r"result", re.IGNORECASE))
        n = loc.count()
    except Exception:
        return None
    for i in range(min(n, 60)):
        try:
            txt = loc.nth(i).inner_text(timeout=400)
        except Exception:
            continue
        val = parse_results_button_text(txt)
        if val is not None:
            return val
    return None


def get_search_page_result_count(
    page: Page,
    *,
    refresh: Callable[[], None],
    timeout_seconds: float = 14.0,
    poll_interval: float = 0.2,
    no_refresh_phase_seconds: float = 3.2,
    min_stable_seconds: float = 0.55,
) -> int:
    """
    After price/rent fields are set (and UI settled), read count from Results button.

    1. Poll without clicking Refresh — Pinergy often updates the Results label in ~1–2s.
    2. If still missing after no_refresh_phase_seconds, click Refresh once and keep polling.
    3. Require the same parsed count for min_stable_seconds before returning, so we do not
       return a stale label from the previous price band.
    """
    deadline = time.time() + timeout_seconds
    refresh_used = False
    phase_end = time.time() + no_refresh_phase_seconds
    stable_val: int | None = None
    stable_since: float | None = None

    while time.time() < deadline:
        val = try_read_results_count(page)
        if val is not None:
            now = time.time()
            if stable_val != val:
                stable_val = val
                stable_since = now
            elif stable_since is not None and (now - stable_since) >= min_stable_seconds:
                return val

        if not refresh_used and time.time() >= phase_end:
            refresh()
            refresh_used = True
            stable_val = None
            stable_since = None

        time.sleep(poll_interval)

    raise ValueError(
        f"Could not read listing count from Results button within {timeout_seconds}s"
    )
