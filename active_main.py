import argparse
import re
from pathlib import Path
import os
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError

from mls_result_count import get_search_page_result_count
from scraper_adaptive import AdaptiveRangeState, find_valid_span
from scraper_resume import MLS_DOWNLOAD_TIMEOUT_HINT, resolved_start_export_resume

# Legacy filename kept for compatibility. Prefer: python3 scrape_mls_active.py

LOGIN_URL = "https://h3l.mlspin.com/signin.asp?#ath"
MAX_RESULTS_SAFE = 950
MAX_PRICE = 10_000_000
ADAPTIVE_MIN_STEP = 1_000
ADAPTIVE_MAX_STEP = 500_000
ADAPTIVE_INITIAL_STEP = 100_000


def click_if_visible(page, name: str, timeout: int = 2500):
    try:
        page.get_by_role("button", name=name).click(timeout=timeout)
        return True
    except TimeoutError:
        return False
    except Exception:
        return False


def _check_status_checkbox(page, *candidate_names: str) -> bool:
    """
    Try each accessible name until one matches. MLS Pinergy labels can vary slightly.
    """
    for name in candidate_names:
        try:
            page.get_by_role("checkbox", name=name).check(timeout=2500)
            print(f"  Status filter on: {name}")
            return True
        except Exception:
            continue
    print(f"  Warning: could not check any of: {candidate_names}")
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


def close_download_modal_if_open(page):
    """Post-download modal (#GenericModal) blocks clicks on Search; must dismiss first."""
    try:
        modal = page.locator("#GenericModal")
        if not modal.is_visible(timeout=2000):
            return

        print("Download modal is open. Closing...")
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
                if btn.is_visible(timeout=800):
                    btn.click(timeout=3000)
                    time.sleep(2)
                    print("Closed download modal.")
                    return
            except Exception:
                pass

        page.keyboard.press("Escape")
        time.sleep(1)
        if not modal.is_visible(timeout=1000):
            print("Closed download modal (Escape).")
    except Exception:
        pass


def _open_search_page_after_login(page) -> None:
    """
    Land on the MLS search UI after sign-in. Dismiss modals first — post-download dialogs block the Search tab.
    Try several locator strategies; Pinergy accessible names occasionally drift slightly.
    """
    close_download_modal_if_open(page)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1.5)

    last_exc: Exception | None = None
    attempts = (
        lambda: page.get_by_role("link", name="Search").click(timeout=90_000),
        lambda: page.get_by_role("link", name=re.compile(r"^\s*Search\s*$", re.I)).click(timeout=30_000),
        lambda: page.get_by_role("link", name=re.compile(r"Search", re.I)).first.click(timeout=30_000),
        lambda: page.locator("a").filter(has_text=re.compile(r"^\s*Search\s*$", re.I)).first.click(timeout=30_000),
    )

    for i, fn in enumerate(attempts):
        close_download_modal_if_open(page)
        try:
            fn()
            page.wait_for_load_state("load")
            wait_for_page_blocker_to_clear(page)
            return
        except Exception as exc:
            last_exc = exc
            print(f"  Search navigation attempt {i + 1}/{len(attempts)} failed: {exc!r}")
            page.keyboard.press("Escape")
            time.sleep(1.5)

    raise TimeoutError(
        "Could not click Search after login (modal blocking or MLS UI changed)."
    ) from last_exc


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
    _open_search_page_after_login(page)


def set_static_filters(page):
    print("Setting active listing filters...")
    wait_for_page_blocker_to_clear(page)

    select_all_types = page.get_by_role("checkbox", name="Select All Property Types")
    try:
        if select_all_types.is_checked():
            select_all_types.uncheck()
        else:
            select_all_types.check(timeout=1000)
            select_all_types.uncheck(timeout=1000)
    except Exception:
        pass

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
    except Exception:
        pass

    # Active inventory + status-change buckets (New, price change, back on market)
    _check_status_checkbox(page, "Active Status")
    _check_status_checkbox(
        page,
        "New Status",
        "New Listing Status",
        "New Listings Status",
    )
    _check_status_checkbox(
        page,
        "Price Change Status",
        "Price Changed Status",
        "New Price Status",
    )
    _check_status_checkbox(
        page,
        "Back on Market Status",
        "Back On Market Status",
    )
    page.locator("body").click(position={"x": 200, "y": 200})
    time.sleep(2)


def ensure_search_form_ready(page):
    close_download_modal_if_open(page)

    try:
        low_box = page.get_by_role("textbox", name="Enter Low Price")
        high_box = page.get_by_role("textbox", name="Enter High Price")
        low_box.wait_for(timeout=3000)
        high_box.wait_for(timeout=3000)
        return
    except Exception:
        pass

    print("Search form not ready. Returning to Search tab...")
    close_download_modal_if_open(page)
    try:
        page.get_by_role("link", name="Search").click(timeout=10000)
    except Exception:
        page.keyboard.press("Escape")
        time.sleep(1)
        close_download_modal_if_open(page)
        page.get_by_role("link", name="Search").click(timeout=15000)
    page.wait_for_load_state("load")
    wait_for_page_blocker_to_clear(page, timeout=30000)
    time.sleep(3)
    set_static_filters(page)


def set_price_range(page, min_price: int, max_price: int):
    ensure_search_form_ready(page)
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
    page.get_by_role("button", name="Refresh Count").nth(1).click()
    wait_for_page_blocker_to_clear(page, timeout=30000)
    time.sleep(0.7)


def find_valid_range(
    page, start_price: int, range_state: AdaptiveRangeState
) -> tuple[int, int]:
    def count_for_range(lo: int, hi: int) -> int:
        ensure_search_form_ready(page)
        set_price_range(page, lo, hi)
        return get_search_page_result_count(page, refresh=lambda: refresh_count(page))

    return find_valid_span(
        start_price,
        MAX_PRICE,
        range_state,
        count_for_range,
        label="active range",
    )


def open_results(page):
    if "/Results?" in page.url:
        return

    wait_for_page_blocker_to_clear(page, timeout=30000)
    for i in [16, 34]:
        try:
            btn = page.locator("button").nth(i)
            txt = btn.inner_text(timeout=1000).strip()
        except Exception:
            txt = ""
        if "results" in " ".join(txt.split()).lower():
            btn.evaluate("el => el.click()")
            page.wait_for_url("**/Results?**", timeout=30000)
            page.wait_for_load_state("load")
            time.sleep(8)
            return
    raise ValueError("Could not navigate to results page.")


def download_current_results(page, save_path: Path):
    select_all = page.get_by_role("checkbox", name="Select all")
    select_all.wait_for(timeout=30000)
    select_all.check()
    time.sleep(2)

    page.get_by_role("button", name="Download Selected Listings").click()
    final_download = page.get_by_role("button", name="Click to download")
    final_download.wait_for(timeout=30000)
    try:
        with page.expect_download(timeout=90_000) as download_info:
            final_download.click()
        download = download_info.value
    except TimeoutError:
        print(MLS_DOWNLOAD_TIMEOUT_HINT)
        close_download_modal_if_open(page)
        raise
    download.save_as(str(save_path))
    print(f"Saved: {save_path}")


def run_one_range(
    page, downloads_dir: Path, start_price: int, range_state: AdaptiveRangeState
) -> int:
    end_price, count = find_valid_range(page, start_price, range_state)
    if count == 0:
        return end_price

    save_path = downloads_dir / f"active_export_{start_price}_{end_price}.csv"
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

    parser = argparse.ArgumentParser(description="MLS active listings export scraper")
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Ignore existing active_export_*.csv files; start from $0.",
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

    downloads_dir = project_dir / "downloads" / "active"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    current_start, last_end = resolved_start_export_resume(
        downloads_dir,
        "active_export_",
        0,
        MAX_PRICE,
        from_start=args.from_start,
    )
    if current_start > MAX_PRICE:
        print(
            "All active bands already have export files (nothing to do). "
            "Use --from-start to re-scrape from $0."
        )
        return
    if last_end is not None:
        print(
            f"Resuming after active_export_* up to end ${last_end:,}; "
            f"next band starts at ${current_start:,}."
        )
        print(
            "Tip: MLS ~100 downloads/day is shared across scrapers — "
            "stagger heavy export days if you hit the cap."
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=200)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        login(page, mls_username, mls_password)
        set_static_filters(page)

        range_state = AdaptiveRangeState(
            step=ADAPTIVE_INITIAL_STEP,
            min_step=ADAPTIVE_MIN_STEP,
            max_step=ADAPTIVE_MAX_STEP,
            max_results_safe=MAX_RESULTS_SAFE,
        )

        while current_start <= MAX_PRICE:
            end_price = run_one_range(page, downloads_dir, current_start, range_state)
            next_start = end_price + 1
            if next_start > MAX_PRICE:
                break
            current_start = next_start
            ensure_search_form_ready(page)

        print("All active ranges complete.")
        if args.interactive:
            input("Press ENTER to close browser...")
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
