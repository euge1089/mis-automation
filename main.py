import argparse
import logging
from pathlib import Path
import os
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError

from mls_result_count import get_search_page_result_count
from scraper_adaptive import AdaptiveRangeState, find_valid_span
from scraper_resume import MLS_DOWNLOAD_TIMEOUT_HINT, resolved_start_export_resume

logger = logging.getLogger(__name__)

# Legacy filename kept for compatibility. Prefer: python3 scrape_mls_sold.py


def _clear_sold_exports(downloads_dir: Path) -> int:
    """Remove prior mls_export_*.csv so the next combine only includes this run."""
    n = 0
    for f in downloads_dir.glob("mls_export_*.csv"):
        f.unlink()
        n += 1
    return n

LOGIN_URL = "https://h3l.mlspin.com/signin.asp?#ath"
MAX_RESULTS_SAFE = 950
MAX_PRICE = 10_000_000
# Fresh sold scrapes begin at this list price (per band lower bound).
SOLD_MIN_PRICE = 180_000
# Adaptive stepping (see scraper_adaptive): min/max cap the probe; initial step seeds the first band.
ADAPTIVE_MIN_STEP = 1_000
ADAPTIVE_MAX_STEP = 500_000
ADAPTIVE_INITIAL_STEP = 100_000


def _detect_mls_daily_download_cap(page) -> bool:
    phrases = (
        "maximum of 100 downloads per day",
        "reached the maximum of 100 downloads per day",
        "please try again tomorrow",
    )
    try:
        body_text = page.locator("body").inner_text(timeout=2000).lower()
    except Exception:
        body_text = ""
    if all(p in body_text for p in ("100 downloads", "try again tomorrow")):
        return True
    if any(p in body_text for p in phrases):
        return True
    try:
        modal_text = page.locator("#GenericModal, .modal-content").inner_text(timeout=1500).lower()
    except Exception:
        modal_text = ""
    return any(p in modal_text for p in phrases)


def click_if_visible(page, name: str, timeout: int = 2500):
    try:
        page.get_by_role("button", name=name).click(timeout=timeout)
        return True
    except TimeoutError:
        return False
    except Exception:
        return False


def wait_for_page_blocker_to_clear(page, timeout=30000):
    blocker = page.locator("#mainPageBlocker")
    try:
        blocker.wait_for(state="hidden", timeout=timeout)
    except Exception:
        try:
            blocker.wait_for(state="detached", timeout=2000)
        except Exception as exc:
            logger.warning("mainPageBlocker did not reach detached state: %s", exc)
    time.sleep(1)


def login(page, username: str, password: str):
    print("Opening MLS login page...")
    page.goto(LOGIN_URL, wait_until="load")

    click_if_visible(page, "OK", timeout=2500)

    print("Logging in...")
    page.get_by_role("textbox", name="Enter Your Agent ID").fill(username)
    page.get_by_role("textbox", name="Password Input").fill(password)
    page.get_by_role("button", name="Sign In").click()

    click_if_visible(page, "Click Here to Continue to", timeout=5000)

    print("Opening search page...")
    page.get_by_role("link", name="Search").click()
    page.wait_for_load_state("load")
    wait_for_page_blocker_to_clear(page)


def set_static_filters(page, timeframe: str):
    print("Setting static search filters...")
    wait_for_page_blocker_to_clear(page)

    select_all_types = page.get_by_role("checkbox", name="Select All Property Types")
    try:
        if select_all_types.is_checked():
            select_all_types.uncheck()
        else:
            select_all_types.check(timeout=1000)
            select_all_types.uncheck(timeout=1000)
    except Exception as exc:
        logger.warning("Select-all property types toggle failed (continuing): %s", exc)

    page.get_by_role("checkbox", name="Single Family Property Type").check()
    page.get_by_role("checkbox", name="Condominium Property Type").check()
    page.get_by_role("checkbox", name="Multi Family Property Type").check()

    select_all_statuses = page.get_by_role("checkbox", name="Select All Statuses")
    try:
        if select_all_statuses.is_checked():
            select_all_statuses.uncheck()
        else:
            select_all_statuses.check(timeout=1000)
            select_all_statuses.uncheck(timeout=1000)
    except Exception as exc:
        logger.warning("Select-all statuses toggle failed (continuing): %s", exc)

    page.get_by_role("checkbox", name="Sold Status").check()

    timeframe_box = page.get_by_role("textbox", name="Off-Market Timeframe")
    timeframe_box.click()
    timeframe_box.press("ControlOrMeta+a")
    timeframe_box.fill(timeframe)

    page.locator("body").click(position={"x": 200, "y": 200})
    time.sleep(2)


def ensure_search_form_ready(page, timeframe: str):
    """
    Make sure we're on a usable search page with visible price inputs.
    If MLS drifted onto results or a partial state, go back to Search.
    """
    try:
        low_box = page.get_by_role("textbox", name="Enter Low Price")
        high_box = page.get_by_role("textbox", name="Enter High Price")
        low_box.wait_for(timeout=3000)
        high_box.wait_for(timeout=3000)
        return
    except Exception as exc:
        logger.warning("Price boxes not visible yet (%s); navigating back to Search.", exc)

    print("Search form not ready. Returning to Search tab...")
    page.get_by_role("link", name="Search").click()
    page.wait_for_load_state("load")
    wait_for_page_blocker_to_clear(page, timeout=30000)
    time.sleep(3)

    set_static_filters(page, timeframe=timeframe)

    page.get_by_role("textbox", name="Enter Low Price").wait_for(timeout=30000)
    page.get_by_role("textbox", name="Enter High Price").wait_for(timeout=30000)


def set_price_range(page, min_price: int, max_price: int, timeframe: str):
    ensure_search_form_ready(page, timeframe=timeframe)

    low_box = page.get_by_role("textbox", name="Enter Low Price")
    high_box = page.get_by_role("textbox", name="Enter High Price")

    low_box.click()
    low_box.press("ControlOrMeta+a")
    low_box.fill(str(min_price))

    high_box.click()
    high_box.press("ControlOrMeta+a")
    high_box.fill(str(max_price))

    page.locator("body").click(position={"x": 200, "y": 200})
    time.sleep(0.7)


def refresh_count(page):
    print("Refreshing count...")
    page.get_by_role("button", name="Refresh Count").nth(1).click()
    wait_for_page_blocker_to_clear(page, timeout=30000)
    time.sleep(0.7)


def find_valid_range(
    page, start_price: int, range_state: AdaptiveRangeState, timeframe: str
) -> tuple[int, int]:
    def count_for_range(lo: int, hi: int) -> int:
        ensure_search_form_ready(page, timeframe=timeframe)
        set_price_range(page, lo, hi, timeframe=timeframe)
        return get_search_page_result_count(page, refresh=lambda: refresh_count(page))

    return find_valid_span(
        start_price,
        MAX_PRICE,
        range_state,
        count_for_range,
        label="range",
    )


def open_results(page):
    if "/Results?" in page.url:
        print("Already on results page.")
        return

    print("Navigating to results page...")
    wait_for_page_blocker_to_clear(page, timeout=30000)

    for i in [16, 34]:
        try:
            btn = page.locator("button").nth(i)
            txt = btn.inner_text(timeout=1000).strip()
        except Exception:
            txt = ""

        txt_clean = " ".join(txt.split())

        if "results" in txt_clean.lower():
            print(f"Clicking results button from button_{i}: {txt_clean!r}")
            btn.evaluate("el => el.click()")
            page.wait_for_url("**/Results?**", timeout=30000)
            page.wait_for_load_state("load")
            time.sleep(10)
            print("Results page loaded.")
            return

    raise ValueError("Could not trigger the Results page from button_16 or button_34.")


def download_current_results(page, save_path: Path):
    print("On results page. Waiting for Select all checkbox...")
    select_all = page.get_by_role("checkbox", name="Select all")
    select_all.wait_for(timeout=30000)

    print("Selecting all listings...")
    select_all.check()
    time.sleep(2)

    print("Clicking download selected listings...")
    page.get_by_role("button", name="Download Selected Listings").click()

    print("Waiting for final download button...")
    final_download = page.get_by_role("button", name="Click to download")
    final_download.wait_for(timeout=30000)

    try:
        with page.expect_download(timeout=90_000) as download_info:
            final_download.click()
        download = download_info.value
    except TimeoutError as exc:
        if _detect_mls_daily_download_cap(page):
            close_download_modal_if_open(page)
            raise RuntimeError(
                "MLS daily download cap reached (100/day). "
                "Stop retries and run again after the cap resets tomorrow."
            ) from exc
        print(MLS_DOWNLOAD_TIMEOUT_HINT)
        close_download_modal_if_open(page)
        raise

    print("Saving download...")
    download.save_as(str(save_path))
    print(f"Saved: {save_path}")


def close_download_modal_if_open(page):
    try:
        modal = page.locator("#GenericModal")
        if modal.is_visible(timeout=3000):
            print("Download modal is open. Trying to close it...")

            close_selectors = [
                'button[aria-label="Close"]',
                'button.close',
                '.modal-header button.close',
                '.modal-header .close',
                '[data-dismiss="modal"]',
            ]

            for selector in close_selectors:
                try:
                    btn = modal.locator(selector).first
                    if btn.is_visible(timeout=1000):
                        btn.click(timeout=3000)
                        time.sleep(2)
                        print("Closed download modal.")
                        return
                except Exception:
                    pass

            print("Could not close download modal automatically.")
    except Exception:
        pass


def return_to_search(page, timeframe: str):
    print("Returning to search page...")
    ensure_search_form_ready(page, timeframe=timeframe)
    print("Back on search page.")


def run_one_range(
    page,
    downloads_dir: Path,
    start_price: int,
    range_state: AdaptiveRangeState,
    timeframe: str,
) -> int:
    end_price, count = find_valid_range(page, start_price, range_state, timeframe=timeframe)

    if count == 0:
        print(f"No results for ${start_price:,} to ${end_price:,}.")
        return end_price

    filename = f"mls_export_{start_price}_{end_price}.csv"
    save_path = downloads_dir / filename

    print(f"Accepted range ${start_price:,} to ${end_price:,} with {count} results")
    open_results(page)
    download_current_results(page, save_path)
    close_download_modal_if_open(page)

    return end_price


def main():
    project_dir = Path(__file__).parent
    load_dotenv(project_dir / ".env")

    mls_username = os.getenv("MLS_USERNAME")
    mls_password = os.getenv("MLS_PASSWORD")

    if not mls_username or not mls_password:
        raise ValueError("Missing MLS_USERNAME or MLS_PASSWORD in .env")

    parser = argparse.ArgumentParser(description="MLS sold-history export scraper")
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Continue from the last saved band (after a partial run). "
            "Default is a fresh run: old mls_export_*.csv files in downloads/ are deleted "
            f"and scraping starts at ${SOLD_MIN_PRICE:,} so combined data reflects only this pull."
        ),
    )
    parser.add_argument(
        "--timeframe",
        default="TODAY - 1 YEAR",
        help=(
            "Value entered into MLS Off-Market Timeframe "
            '(example: "TODAY - 1 YEAR" or "01/01/2026 - 01/31/2026").'
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (preferred for hosted scheduling).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Pause for ENTER before closing browser.",
    )
    args = parser.parse_args()

    downloads_dir = project_dir / "downloads"
    downloads_dir.mkdir(exist_ok=True)

    if args.resume:
        current_start, last_end = resolved_start_export_resume(
            downloads_dir,
            "mls_export_",
            SOLD_MIN_PRICE,
            MAX_PRICE,
            from_start=False,
        )
        if current_start > MAX_PRICE:
            print(
                "All sold bands already have export files (nothing to do). "
                "Delete mls_export_*.csv in downloads/ or run without --resume for a fresh scrape."
            )
            return
        if last_end is not None:
            print(
                f"Resuming after mls_export_* up to end ${last_end:,}; "
                f"next band starts at ${current_start:,}."
            )
            print(
                "Tip: MLS ~100 downloads/day is shared across scrapers — "
                "run sold and rentals on different days if you hit the cap."
            )
    else:
        removed = _clear_sold_exports(downloads_dir)
        if removed:
            print(f"Fresh run: removed {removed} previous sold export file(s) from downloads/.")
        else:
            print("Fresh run: no previous mls_export_*.csv files in downloads/.")
        current_start = SOLD_MIN_PRICE

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=200)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        login(page, mls_username, mls_password)
        set_static_filters(page, timeframe=args.timeframe)

        range_state = AdaptiveRangeState(
            step=ADAPTIVE_INITIAL_STEP,
            min_step=ADAPTIVE_MIN_STEP,
            max_step=ADAPTIVE_MAX_STEP,
            max_results_safe=MAX_RESULTS_SAFE,
        )

        chunk_num = 1

        while current_start <= MAX_PRICE:
            print(f"\n--- RANGE {chunk_num} ---")
            end_price = run_one_range(
                page,
                downloads_dir,
                current_start,
                range_state,
                timeframe=args.timeframe,
            )

            next_start = end_price + 1
            if next_start > MAX_PRICE:
                break

            print(f"Completed range ${current_start:,} to ${end_price:,}.")
            print(f"Next start price: ${next_start:,}")

            current_start = next_start
            chunk_num += 1

            return_to_search(page, timeframe=args.timeframe)

        print("\nAll ranges complete.")
        if args.interactive:
            input("Press ENTER to close the browser...")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
