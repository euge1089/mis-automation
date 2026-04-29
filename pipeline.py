import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from combine_csv import combine_sold_exports
from combine_rentals import combine_rental_exports
from combine_active import combine_active_exports
from clean_data import run_cleaning_jobs
from build_rent_model import build_rent_models
from data_quality import validate_monthly_outputs, validate_daily_active_outputs
from snapshot_manager import create_monthly_snapshot, create_daily_active_snapshot
from historical_policy import (
    DateWindow,
    backfill_window,
    hot_window,
    iter_month_windows,
    memorialize_through,
    to_mls_timeframe,
)
from load_to_db import memorialize_history_window
from backend.db import Base, SessionLocal, engine


PROJECT_DIR = Path(__file__).parent
CHECKPOINT_DIR = PROJECT_DIR / "history" / "checkpoints"
BACKFILL_CHECKPOINT = CHECKPOINT_DIR / "backfill_historical.json"
MEMORIALIZATION_STATE = CHECKPOINT_DIR / "memorialization_state.json"


def _run_script(script_name: str, args: list[str] | None = None, *, role: str = "Running") -> None:
    cmd = [sys.executable, script_name]
    if args:
        cmd.extend(args)
    print(f"{role}: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _run_sold_rented_scrape_for_window(
    *,
    window: DateWindow,
    run_scrapers: bool,
    headless: bool,
) -> None:
    timeframe = to_mls_timeframe(window)
    if run_scrapers:
        sold_args = ["--timeframe", timeframe]
        rented_args = ["--timeframe", timeframe, "--from-start"]
        if headless:
            sold_args.append("--headless")
            rented_args.append("--headless")
        _run_script("scrape_mls_sold.py", sold_args, role="Scraper")
        _run_script("scrape_mls_rented.py", rented_args, role="Scraper")

    combine_sold_exports()
    combine_rental_exports()
    run_cleaning_jobs(
        jobs=[
            ("sold_master_latest.csv", "sold_clean_latest.csv"),
            ("rentals_master_latest.csv", "rentals_clean_latest.csv"),
        ]
    )


def _memorialize_window(window: DateWindow) -> tuple[int, int]:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        sold_count, rented_count = memorialize_history_window(
            session,
            window_start=window.start,
            window_end=window.end,
            as_of=datetime.now(timezone.utc),
        )
        session.commit()
    print(
        "Memorialized window "
        f"{window.start}..{window.end}: sold={sold_count:,}, rented={rented_count:,}"
    )
    return sold_count, rented_count


def run_monthly_pipeline(run_scrapers: bool) -> None:
    print("=== MONTHLY PIPELINE START ===")
    if run_scrapers:
        _run_script("scrape_mls_sold.py", role="Scraper")
        _run_script("scrape_mls_rented.py", role="Scraper")

    combine_sold_exports()
    combine_rental_exports()

    run_cleaning_jobs(
        jobs=[
            ("sold_master_latest.csv", "sold_clean_latest.csv"),
            ("rentals_master_latest.csv", "rentals_clean_latest.csv"),
        ]
    )
    build_rent_models()
    validate_monthly_outputs()
    create_monthly_snapshot()
    print("=== MONTHLY PIPELINE COMPLETE ===")


def run_daily_active_pipeline(run_scraper: bool, *, headless: bool = False) -> None:
    print("=== DAILY ACTIVE PIPELINE START ===")
    if run_scraper:
        active_args = ["--headless"] if headless else []
        _run_script("scrape_mls_active.py", active_args, role="Scraper")

    try:
        combine_active_exports()
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{exc} Run with --with-scrape or place active_export_*.csv files in downloads/active."
        ) from exc

    run_cleaning_jobs(jobs=[("active_latest.csv", "active_clean_latest.csv")])
    validate_daily_active_outputs()
    create_daily_active_snapshot()
    print("=== DAILY ACTIVE PIPELINE COMPLETE ===")


def run_daily_active_pipeline_with_geocode(
    run_scraper: bool, run_geocode: bool, *, headless: bool = False
) -> None:
    run_daily_active_pipeline(run_scraper=run_scraper, headless=headless)
    if run_geocode:
        _run_script("geocode_active.py", role="Geocoder")
        _run_script("load_to_db.py", role="DB loader")


def run_backfill_historical(
    *,
    years: int,
    run_scrapers: bool,
    headless: bool,
    resume: bool,
) -> None:
    print("=== BACKFILL HISTORICAL START ===")
    target = backfill_window(years=years)
    windows = iter_month_windows(target.start, target.end)
    if not windows:
        print("No backfill windows to process.")
        return

    if resume:
        state = _load_json(BACKFILL_CHECKPOINT)
        last_end = state.get("last_completed_window_end")
        if last_end:
            last_completed = date.fromisoformat(last_end)
            windows = [w for w in windows if w.end > last_completed]
            print(f"Resuming after {last_completed}; remaining windows: {len(windows)}")

    for window in windows:
        print(f"Processing backfill window {window.start}..{window.end}")
        _run_sold_rented_scrape_for_window(window=window, run_scrapers=run_scrapers, headless=headless)
        _memorialize_window(window)
        _save_json(
            BACKFILL_CHECKPOINT,
            {
                "last_completed_window_start": window.start.isoformat(),
                "last_completed_window_end": window.end.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    print("=== BACKFILL HISTORICAL COMPLETE ===")


def run_weekly_sold_rented(
    *,
    run_scrapers: bool,
    headless: bool,
) -> None:
    print("=== WEEKLY SOLD/RENTED START ===")
    cutoff = memorialize_through()
    state = _load_json(MEMORIALIZATION_STATE)
    last_end_str = state.get("last_memorialized_through")
    if last_end_str:
        start = date.fromisoformat(last_end_str) + date.resolution
    else:
        # If never memorialized, start from first month in 5-year span.
        start = backfill_window(years=5).start
    if start <= cutoff:
        for window in iter_month_windows(start, cutoff):
            print(f"Memorialization catch-up window: {window.start}..{window.end}")
            _run_sold_rented_scrape_for_window(
                window=window,
                run_scrapers=run_scrapers,
                headless=headless,
            )
            _memorialize_window(window)
            _save_json(
                MEMORIALIZATION_STATE,
                {
                    "last_memorialized_through": window.end.isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    else:
        print(f"No new memorialization month available (current cutoff: {cutoff}).")

    # Refresh rolling hot window used for current analytics.
    hot = hot_window()
    print(f"Refreshing hot window {hot.start}..{hot.end}")
    _run_sold_rented_scrape_for_window(window=hot, run_scrapers=run_scrapers, headless=headless)
    build_rent_models()
    validate_monthly_outputs()
    _run_script("load_to_db.py", role="DB loader")
    create_monthly_snapshot()
    print("=== WEEKLY SOLD/RENTED COMPLETE ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="MLS automation pipeline runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    monthly = subparsers.add_parser(
        "monthly", help="Run monthly historical pipeline (sold + rentals)"
    )
    monthly.add_argument(
        "--with-scrape",
        action="store_true",
        help="Run MLS browser scraping before combine/clean/model steps",
    )

    weekly = subparsers.add_parser(
        "weekly-sold-rented",
        help="Weekly MLS sold/rented refresh with memorialization cutoff policy",
    )
    weekly.add_argument(
        "--no-scrape",
        action="store_true",
        help="Skip MLS scraping and only process existing files.",
    )
    weekly.add_argument(
        "--headless",
        action="store_true",
        help="Pass --headless to scraping scripts.",
    )

    backfill = subparsers.add_parser(
        "backfill-historical",
        help="One-time cap-aware monthly backfill over historical windows",
    )
    backfill.add_argument("--years", type=int, default=5, help="Backfill N years (default: 5).")
    backfill.add_argument(
        "--no-scrape",
        action="store_true",
        help="Skip MLS scraping and only process existing files for each window.",
    )
    backfill.add_argument(
        "--headless",
        action="store_true",
        help="Pass --headless to scraping scripts.",
    )
    backfill.add_argument(
        "--resume",
        action="store_true",
        help="Resume from history/checkpoints/backfill_historical.json",
    )

    daily = subparsers.add_parser(
        "daily-active", help="Run daily active listings pipeline"
    )
    daily.add_argument(
        "--with-scrape",
        action="store_true",
        help="Run active MLS browser scraping before combine/clean steps",
    )
    daily.add_argument(
        "--with-geocode",
        action="store_true",
        help="Geocode active listings after cleaning and load to DB",
    )
    daily.add_argument(
        "--headless",
        action="store_true",
        help="Pass --headless to active scraping script.",
    )

    subparsers.add_parser("validate-monthly", help="Validate monthly outputs only")
    subparsers.add_parser("validate-daily-active", help="Validate daily-active outputs only")
    subparsers.add_parser("load-db", help="Load cleaned/analytics outputs into Postgres")
    subparsers.add_parser("geocode-active", help="Geocode active_clean_latest.csv addresses")

    args = parser.parse_args()

    if args.command == "monthly":
        run_monthly_pipeline(run_scrapers=args.with_scrape)
    elif args.command == "weekly-sold-rented":
        run_weekly_sold_rented(
            run_scrapers=not args.no_scrape,
            headless=args.headless,
        )
    elif args.command == "backfill-historical":
        run_backfill_historical(
            years=args.years,
            run_scrapers=not args.no_scrape,
            headless=args.headless,
            resume=args.resume,
        )
    elif args.command == "daily-active":
        run_daily_active_pipeline_with_geocode(
            run_scraper=args.with_scrape,
            run_geocode=args.with_geocode,
            headless=args.headless,
        )
    elif args.command == "validate-monthly":
        validate_monthly_outputs()
    elif args.command == "validate-daily-active":
        validate_daily_active_outputs()
    elif args.command == "load-db":
        _run_script("load_to_db.py", role="DB loader")
    elif args.command == "geocode-active":
        _run_script("geocode_active.py", role="Geocoder")


if __name__ == "__main__":
    main()
