#!/usr/bin/env python3
"""
Collect Zillow *for rent* search results into a rolling CSV archive (keyed by zpid).

Deprecated
----------
This script is no longer part of the active rentals pipeline.
The production path uses MLS-only rentals data.

Important
---------
- Zillow's Terms of Use restrict automated access. This script is for personal research only;
  use slow, respectful pacing, and expect DOM or anti-bot changes to break it without notice.
- Zillow search is mostly **current rentals**, not a full "rented in the past year" ledger.
  Re-scraping regularly records what was on the market; when a listing vanishes, its row stops
  getting ``last_seen_utc`` updates and is eventually pruned (default: not seen for 365 days).

Environment
-----------
- ``ZILLOW_RENTAL_SEARCH_URL`` — default search (e.g. state or city rentals page).
- ``ZILLOW_RENTAL_SEARCH_URLS`` — comma-separated list overrides the default when set.

Typical run (weekly cron, headed browser often survives bot checks better):

  python3 zillow_rentals_main.py

Custom search + archive path:

  python3 zillow_rentals_main.py \\
    --search-url 'https://www.zillow.com/boston-ma/rentals/' \\
    --archive data/zillow/rentals_archive.csv
"""
from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from zillow_rental_archive import (
    default_archive_path,
    load_archive,
    merge_snapshot,
    prune_stale,
    save_archive,
)

LISTING_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const nodes = document.querySelectorAll('a[href*="/homedetails/"]');
  for (const a of nodes) {
    let href = a.getAttribute("href") || "";
    if (!href.includes("_zpid")) continue;
    const m = href.match(/(\d+)_zpid/);
    if (!m) continue;
    const zpid = m[1];
    if (seen.has(zpid)) continue;
    seen.add(zpid);
    if (!href.startsWith("http")) href = "https://www.zillow.com" + href;
    const card =
      a.closest("article") ||
      a.closest("[data-testid=\"property-card\"]") ||
      a.closest("li") ||
      a.parentElement;
    const text = card ? card.innerText : (a.innerText || "");
    out.push({
      zpid,
      href: href.split("?")[0],
      cardText: text.slice(0, 2500),
    });
  }
  return out;
}
"""


def parse_card_text(text: str) -> dict[str, Any]:
    """Best-effort parse of Zillow card plain text (layout varies)."""
    rent: float | None = None
    m = re.search(r"\$\s*([\d,]+)\s*\+?(?:\s*/\s*mo)?", text, re.I)
    if m:
        rent = float(m.group(1).replace(",", ""))

    beds: float | None = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*bds?\b", text, re.I)
    if m:
        beds = float(m.group(1))

    baths: float | None = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*ba\b", text, re.I)
    if m:
        baths = float(m.group(1))

    sqft: float | None = None
    m = re.search(r"([\d,]+)\s*sqft\b", text, re.I)
    if m:
        sqft = float(m.group(1).replace(",", ""))

    zip_code = ""
    zm = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
    if zm:
        zip_code = zm.group(1)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    address = ""
    city_state = ""
    for ln in lines:
        if ln.startswith("$") and "/mo" in ln.lower():
            continue
        if re.match(r"^\$\s*[\d,]+", ln):
            continue
        if re.search(r"\d+\s*bds?\b", ln, re.I) and "sqft" in ln.lower():
            continue
        if re.fullmatch(r"[\d,]+\s*sqft", ln, re.I):
            continue
        if "available" in ln.lower() and len(ln) < 40:
            continue
        if len(ln) > 6:
            address = ln
            break
    for ln in lines:
        if re.search(r",\s*[A-Z]{2}\s+\d{5}", ln):
            city_state = ln
            break

    return {
        "address": address[:500] if address else "",
        "city_state": city_state[:200] if city_state else "",
        "zip_code": zip_code,
        "rent": rent,
        "beds": beds,
        "baths": baths,
        "sqft": sqft,
    }


def dismiss_common_overlays(page) -> None:
    for name in ("Accept all", "Accept", "I Agree", "Close"):
        try:
            loc = page.get_by_role("button", name=name)
            if loc.count() > 0:
                loc.first.click(timeout=2500)
                time.sleep(0.5)
                return
        except Exception:
            pass


def collect_once(page) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = page.evaluate(LISTING_JS)
    rows = []
    for item in raw:
        card = item.get("cardText") or ""
        fields = parse_card_text(card)
        rows.append(
            {
                "zpid": str(item["zpid"]),
                "detail_url": item.get("href", ""),
                **fields,
            }
        )
    return rows


def scroll_and_collect(
    page,
    *,
    max_scrolls: int,
    settle_s: float,
    stagnant_limit: int,
) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    stagnant = 0
    for _ in range(max_scrolls):
        before = len(seen)
        for row in collect_once(page):
            seen[row["zpid"]] = row
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        time.sleep(settle_s)
        after = len(seen)
        if after == before:
            stagnant += 1
            if stagnant >= stagnant_limit:
                break
        else:
            stagnant = 0
    return list(seen.values())


def try_click_next_page(page) -> bool:
    selectors = [
        'a[aria-label="Go to next page"]',
        'a[title="Next page"]',
        'a[data-testid="pagination-page-next"]',
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if loc.is_visible(timeout=1500):
                loc.click(timeout=5000)
                time.sleep(2.5)
                return True
        except Exception:
            continue
    return False


def scrape_search_url(
    page,
    url: str,
    *,
    max_scrolls: int,
    max_pages: int,
    settle_s: float,
) -> list[dict[str, Any]]:
    print(f"Opening {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    time.sleep(2.0)
    dismiss_common_overlays(page)

    all_rows: dict[str, dict[str, Any]] = {}
    for page_idx in range(max_pages):
        print(f"  Page/scrape segment {page_idx + 1}/{max_pages} — scrolling…")
        chunk = scroll_and_collect(
            page,
            max_scrolls=max_scrolls,
            settle_s=settle_s,
            stagnant_limit=3,
        )
        for r in chunk:
            all_rows[r["zpid"]] = r
        print(f"  -> {len(all_rows)} unique zpids so far")
        if page_idx + 1 >= max_pages:
            break
        if not try_click_next_page(page):
            print("  No further pagination control found; stopping.")
            break

    return list(all_rows.values())


def resolve_search_urls(explicit: list[str]) -> list[str]:
    multi = os.getenv("ZILLOW_RENTAL_SEARCH_URLS", "").strip()
    if multi:
        return [u.strip() for u in multi.split(",") if u.strip()]
    single = os.getenv("ZILLOW_RENTAL_SEARCH_URL", "").strip()
    if single:
        return [single]
    if explicit:
        return explicit
    return ["https://www.zillow.com/ma/rentals/"]


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    load_dotenv(project_dir / ".env")

    parser = argparse.ArgumentParser(
        description="Scrape Zillow for-rent search into a rolling zpid archive (CSV)."
    )
    parser.add_argument(
        "--search-url",
        action="append",
        dest="search_urls",
        metavar="URL",
        help="Rentals search URL (repeatable). Default: ZILLOW_RENTAL_* env or MA statewide.",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=None,
        help="CSV path for the rolling archive (default: data/zillow/rentals_archive.csv).",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="Do not remove rows unseen longer than --prune-stale-days.",
    )
    parser.add_argument(
        "--prune-stale-days",
        type=int,
        default=365,
        help="Drop rows whose last_seen_utc is older than this many days (default: 365).",
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=30,
        help="Max scroll iterations per page while loading infinite-scroll results.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Max pagination clicks (next page) per search URL.",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=2.0,
        help="Pause after each scroll for content to load.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless (more likely to hit bot challenges).",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Playwright slow_mo ms (e.g. 100) for steadier UI.",
    )
    parser.add_argument(
        "--sleep-between-urls",
        type=float,
        default=8.0,
        help="Seconds to wait between multiple search URLs.",
    )
    args = parser.parse_args()

    archive_path = args.archive or default_archive_path(project_dir)
    urls = resolve_search_urls(args.search_urls or [])

    all_rows: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = context.new_page()
        try:
            for i, url in enumerate(urls):
                if i > 0:
                    print(f"Sleeping {args.sleep_between_urls}s before next URL…")
                    time.sleep(args.sleep_between_urls)
                all_rows.extend(
                    scrape_search_url(
                        page,
                        url,
                        max_scrolls=args.max_scrolls,
                        max_pages=args.max_pages,
                        settle_s=args.settle_seconds,
                    )
                )
        finally:
            context.close()
            browser.close()

    new_df = pd.DataFrame(all_rows)
    if new_df.empty:
        print("No listings parsed from page (selectors may have changed or page blocked).")
    else:
        print(f"Parsed {len(new_df)} listings this run.")

    existing = load_archive(archive_path)
    merged = merge_snapshot(existing, new_df)
    removed = 0
    if not args.no_prune and args.prune_stale_days > 0:
        merged, removed = prune_stale(merged, stale_days=args.prune_stale_days)
        if removed:
            print(f"Pruned {removed} row(s) not seen in {args.prune_stale_days} days.")

    save_archive(merged, archive_path)
    print(f"Archive saved: {archive_path} ({len(merged):,} rows)")


if __name__ == "__main__":
    main()
