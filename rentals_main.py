"""
MLS rented-history export scraper.

This project currently uses MLS as the source of truth for rentals data.
"""
import argparse
from datetime import datetime
from pathlib import Path
import os
import re
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError

from mls_result_count import get_search_page_result_count
from scraper_adaptive import AdaptiveRangeState, find_valid_span
from scraper_resume import MLS_DOWNLOAD_TIMEOUT_HINT, resolved_start_export_resume

# Legacy filename kept for compatibility. Prefer: python3 scrape_mls_rented.py

LOGIN_URL = "https://h3l.mlspin.com/signin.asp?#ath"
MAX_RESULTS_SAFE = 950
MAX_RENT = 20_000
MIN_RENT = 700
ADAPTIVE_MIN_STEP = 25
ADAPTIVE_MAX_STEP = 2_500
ADAPTIVE_INITIAL_STEP = 1_000
PROJECT_DIR = Path(__file__).parent
LOGIN_SEARCH_RETRIES = 2


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


def _clear_rental_exports(downloads_dir: Path) -> int:
    n = 0
    for f in downloads_dir.glob("rentals_export_*.csv"):
        f.unlink()
        n += 1
    return n


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
        except Exception:
            pass
    time.sleep(1)


def _clear_sign_in_violation_notice(page) -> bool:
    try:
        body_text = page.locator("body").inner_text(timeout=2000).lower()
    except Exception:
        body_text = ""
    if "sign-in violation notice" not in body_text and "disconnected the previous sign-in" not in body_text:
        return False

    print("Detected Sign-In Violation Notice; continuing to Pinergy...")
    clickers = (
        lambda: page.get_by_role("button", name=re.compile(r"continue to pinergy", re.I)).click(timeout=5000),
        lambda: page.get_by_role("button", name=re.compile(r"click here to continue", re.I)).click(timeout=5000),
        lambda: page.get_by_role("link", name=re.compile(r"continue to pinergy", re.I)).click(timeout=5000),
    )
    for fn in clickers:
        try:
            fn()
            page.wait_for_load_state("load")
            time.sleep(1.2)
            return True
        except Exception:
            continue
    print("Warning: Sign-In Violation Notice detected but could not click continue button.")
    return False


def _open_search_page_after_login(page) -> None:
    _clear_sign_in_violation_notice(page)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1.2)
    last_exc: Exception | None = None
    attempts = (
        lambda: page.get_by_role("link", name="Search").click(timeout=90_000),
        lambda: page.get_by_role("link", name=re.compile(r"^\s*Search\s*$", re.I)).click(timeout=30_000),
        lambda: page.get_by_role("link", name=re.compile(r"Search", re.I)).first.click(timeout=30_000),
        lambda: page.locator("a").filter(has_text=re.compile(r"^\s*Search\s*$", re.I)).first.click(timeout=30_000),
    )
    for i, fn in enumerate(attempts):
        _clear_sign_in_violation_notice(page)
        try:
            fn()
            page.wait_for_load_state("load")
            wait_for_page_blocker_to_clear(page)
            return
        except Exception as exc:
            last_exc = exc
            print(f"  Search navigation attempt {i + 1}/{len(attempts)} failed: {exc!r}")
            page.keyboard.press("Escape")
            time.sleep(1.2)
    _dump_search_timeout_artifacts(page, scraper_name="rented")
    raise TimeoutError("Could not click Search after login (modal blocking or MLS UI changed).") from last_exc


def _dump_search_timeout_artifacts(page, *, scraper_name: str) -> None:
    debug_dir = PROJECT_DIR / "logs" / "scraper_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    base = f"{scraper_name}_search_timeout_{stamp}"
    screenshot_path = debug_dir / f"{base}.png"
    html_path = debug_dir / f"{base}.html"
    meta_path = debug_dir / f"{base}.txt"
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as exc:
        print(f"Warning: could not save timeout screenshot: {exc!r}")
    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception as exc:
        print(f"Warning: could not save timeout HTML: {exc!r}")
    try:
        meta = [
            f"url={page.url}",
            f"title={page.title() if hasattr(page, 'title') else ''}",
            f"saved_screenshot={screenshot_path}",
            f"saved_html={html_path}",
        ]
        meta_path.write_text("\n".join(meta) + "\n", encoding="utf-8")
        print(f"Saved search-timeout debug artifacts: {meta_path}")
    except Exception as exc:
        print(f"Warning: could not save timeout metadata: {exc!r}")


def login(page, username: str, password: str):
    last_exc: Exception | None = None
    for attempt in range(1, LOGIN_SEARCH_RETRIES + 1):
        print("Opening MLS login page...")
        page.goto(LOGIN_URL, wait_until="load")

        click_if_visible(page, "OK", timeout=2500)

        print("Logging in...")
        page.get_by_role("textbox", name="Enter Your Agent ID").fill(username)
        page.get_by_role("textbox", name="Password Input").fill(password)
        page.get_by_role("button", name="Sign In").click()

        click_if_visible(page, "Click Here to Continue to", timeout=5000)

        print("Opening search page...")
        try:
            _open_search_page_after_login(page)
            return
        except TimeoutError as exc:
            last_exc = exc
            if attempt >= LOGIN_SEARCH_RETRIES:
                break
            print(
                f"Login/search attempt {attempt}/{LOGIN_SEARCH_RETRIES} failed; "
                "retrying a full login once."
            )
            page.keyboard.press("Escape")
            time.sleep(2)
    if last_exc is not None:
        raise last_exc


def set_static_filters(page, timeframe: str):
    print("Setting rental search filters...")
    wait_for_page_blocker_to_clear(page)

    # Clear property types first
    select_all_types = page.get_by_role("checkbox", name="Select All Property Types")
    try:
        if select_all_types.is_checked():
            select_all_types.uncheck()
        else:
            select_all_types.check(timeout=1000)
            select_all_types.uncheck(timeout=1000)
    except Exception:
        pass

    # Only Residential Rental
    page.get_by_role("checkbox", name="Residential Rental Property Type").check()

    # Clear statuses first
    select_all_statuses = page.get_by_role("checkbox", name="Select All Statuses")
    try:
        if select_all_statuses.is_checked():
            select_all_statuses.uncheck()
        else:
            select_all_statuses.check(timeout=1000)
            select_all_statuses.uncheck(timeout=1000)
    except Exception:
        pass

    # Only Rented
    page.get_by_role("checkbox", name="Rented Status").check()

    # Historical timeframe
    timeframe_box = page.get_by_role("textbox", name="Off-Market Timeframe")
    timeframe_box.click()
    timeframe_box.press("ControlOrMeta+a")
    timeframe_box.fill(timeframe)

    page.locator("body").click(position={"x": 200, "y": 200})
    time.sleep(2)


def ensure_search_form_ready(page, timeframe: str):
    try:
        low_box = page.get_by_role("textbox", name="Enter Low Price")
        high_box = page.get_by_role("textbox", name="Enter High Price")
        low_box.wait_for(timeout=3000)
        high_box.wait_for(timeout=3000)
        return
    except Exception:
        pass

    print("Search form not ready. Returning to Search tab...")
    page.get_by_role("link", name="Search").click()
    page.wait_for_load_state("load")
    wait_for_page_blocker_to_clear(page, timeout=30000)
    time.sleep(3)

    set_static_filters(page, timeframe=timeframe)

    page.get_by_role("textbox", name="Enter Low Price").wait_for(timeout=30000)
    page.get_by_role("textbox", name="Enter High Price").wait_for(timeout=30000)


def set_rent_range(page, min_rent: int, max_rent: int, timeframe: str):
    ensure_search_form_ready(page, timeframe=timeframe)

    low_box = page.get_by_role("textbox", name="Enter Low Price")
    high_box = page.get_by_role("textbox", name="Enter High Price")

    low_box.click()
    low_box.press("ControlOrMeta+a")
    low_box.fill(str(min_rent))

    high_box.click()
    high_box.press("ControlOrMeta+a")
    high_box.fill(str(max_rent))

    page.locator("body").click(position={"x": 200, "y": 200})
    time.sleep(0.7)


def refresh_count(page):
    print("Refreshing count...")
    page.get_by_role("button", name="Refresh Count").nth(1).click()
    wait_for_page_blocker_to_clear(page, timeout=30000)
    time.sleep(0.7)


def find_valid_range(
    page, start_rent: int, range_state: AdaptiveRangeState, timeframe: str
) -> tuple[int, int]:
    def count_for_range(lo: int, hi: int) -> int:
        ensure_search_form_ready(page, timeframe=timeframe)
        set_rent_range(page, lo, hi, timeframe=timeframe)
        return get_search_page_result_count(page, refresh=lambda: refresh_count(page))

    return find_valid_span(
        start_rent,
        MAX_RENT,
        range_state,
        count_for_range,
        label="rent range",
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
    start_rent: int,
    range_state: AdaptiveRangeState,
    timeframe: str,
) -> int:
    end_rent, count = find_valid_range(page, start_rent, range_state, timeframe=timeframe)

    if count == 0:
        print(f"No results for ${start_rent:,} to ${end_rent:,}.")
        return end_rent

    filename = f"rentals_export_{start_rent}_{end_rent}.csv"
    save_path = downloads_dir / filename

    print(f"Accepted range ${start_rent:,} to ${end_rent:,} with {count} results")
    open_results(page)
    download_current_results(page, save_path)
    close_download_modal_if_open(page)

    return end_rent


def main():
    project_dir = Path(__file__).parent
    load_dotenv(project_dir / ".env")

    mls_username = os.getenv("MLS_USERNAME")
    mls_password = os.getenv("MLS_PASSWORD")

    if not mls_username or not mls_password:
        raise ValueError("Missing MLS_USERNAME or MLS_PASSWORD in .env")

    parser = argparse.ArgumentParser(description="MLS rented-history export scraper")
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Ignore existing rentals_export_*.csv files; start from the minimum rent.",
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

    downloads_dir = project_dir / "downloads" / "rentals"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    if args.from_start:
        removed = _clear_rental_exports(downloads_dir)
        if removed:
            print(f"Removed {removed} previous rentals_export_*.csv file(s).")

    current_start, last_end = resolved_start_export_resume(
        downloads_dir,
        "rentals_export_",
        MIN_RENT,
        MAX_RENT,
        from_start=args.from_start,
    )
    if current_start > MAX_RENT:
        print(
            "All rental bands already have export files (nothing to do). "
            f"Use --from-start to re-scrape from ${MIN_RENT:,}."
        )
        return
    if last_end is not None:
        print(
            f"Resuming after rentals_export_* up to end ${last_end:,}; "
            f"next band starts at ${current_start:,}."
        )
        print(
            "Tip: MLS ~100 downloads/day is shared across scrapers — "
            "run sold and rentals on different days if you hit the cap."
        )

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

        while current_start <= MAX_RENT:
            print(f"\n--- RENT RANGE {chunk_num} ---")
            end_rent = run_one_range(
                page,
                downloads_dir,
                current_start,
                range_state,
                timeframe=args.timeframe,
            )

            next_start = end_rent + 1
            if next_start > MAX_RENT:
                break

            print(f"Completed range ${current_start:,} to ${end_rent:,}.")
            print(f"Next start rent: ${next_start:,}")

            current_start = next_start
            chunk_num += 1

            return_to_search(page, timeframe=args.timeframe)

        print("\nAll rental ranges complete.")
        if args.interactive:
            input("Press ENTER to close the browser...")

        context.close()
        browser.close()


if __name__ == "__main__":
    main()
