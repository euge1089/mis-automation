import argparse
from argparse import Namespace
import json
import os
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
from storage_paths import clear_active_raw_downloads, clear_sold_and_rental_raw_downloads
from historical_policy import (
    DateWindow,
    backfill_window,
    iter_month_windows,
    rolling_three_month_window,
    to_mls_timeframe,
)
from load_to_db import append_history_window, memorialize_history_window
from backend.db import Base, SessionLocal, engine


PROJECT_DIR = Path(__file__).parent
CHECKPOINT_DIR = PROJECT_DIR / "history" / "checkpoints"
BACKFILL_CHECKPOINT = CHECKPOINT_DIR / "backfill_historical.json"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


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


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return default


def _scrape_requested(args: Namespace) -> bool:
    if args.command == "daily-active":
        return bool(args.with_scrape)
    if args.command == "monthly":
        return bool(args.with_scrape)
    if args.command in {"weekly-sold-rented", "backfill-historical", "adhoc-history-window"}:
        return not bool(args.no_scrape)
    return False


def _enforce_scrape_lock(args: Namespace) -> None:
    # Default allows scraping. Set MLS_SCRAPE_ENABLED=0 to hard-stop MLS login/download commands.
    scrape_enabled = _env_flag("MLS_SCRAPE_ENABLED", default=True)
    if scrape_enabled or not _scrape_requested(args):
        return
    raise RuntimeError(
        "MLS scraping is disabled by MLS_SCRAPE_ENABLED=0. "
        "This command was about to run a live MLS scrape. "
        "Run without scrape flags (e.g. --no-scrape), or set MLS_SCRAPE_ENABLED=1 when quota resets."
    )


def _run_sold_rented_scrape_for_window(
    *,
    window: DateWindow,
    run_scrapers: bool,
    headless: bool,
) -> None:
    timeframe = to_mls_timeframe(window)
    if run_scrapers:
        cleared = clear_sold_and_rental_raw_downloads(PROJECT_DIR)
        print(
            "Cleared raw sold/rental downloads before scrape: "
            f"sold={cleared['sold']} file(s), rentals={cleared['rentals']} file(s)"
        )
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


def _parse_iso_date(raw: str, *, arg_name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:  # pragma: no cover - simple argparse-like error surface
        raise ValueError(f"{arg_name} must be YYYY-MM-DD (got {raw!r})") from exc


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
        cleared = clear_sold_and_rental_raw_downloads(PROJECT_DIR)
        print(
            "Cleared raw sold/rental downloads before scrape: "
            f"sold={cleared['sold']} file(s), rentals={cleared['rentals']} file(s)"
        )
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
    create_monthly_snapshot(folder_name=f"data-{date.today():%Y-%m}-monthly-run")
    print("=== MONTHLY PIPELINE COMPLETE ===")


def run_daily_active_pipeline(
    run_scraper: bool, *, headless: bool = False, from_start: bool = False
) -> None:
    print("=== DAILY ACTIVE PIPELINE START ===")
    if run_scraper:
        removed = clear_active_raw_downloads(PROJECT_DIR)
        print(
            "Cleared prior active MLS slice files before scrape: "
            f"{removed} file(s) removed from downloads/active/"
        )
        active_args: list[str] = []
        if headless:
            active_args.append("--headless")
        if from_start:
            active_args.append("--from-start")
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
    run_scraper: bool,
    run_geocode: bool,
    run_load_db: bool,
    *,
    headless: bool = False,
    from_start: bool = False,
) -> None:
    run_daily_active_pipeline(run_scraper=run_scraper, headless=headless, from_start=from_start)
    if run_geocode:
        _run_script("geocode_active.py", role="Geocoder")
    if run_load_db:
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
        create_monthly_snapshot(folder_name=f"data-{window.end:%Y-%m}")
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
    rolling = rolling_three_month_window()
    print(
        f"Rolling 3-month MLS window {rolling.start:%Y-%m-%d} .. {rolling.end:%Y-%m-%d} "
        "(raw sold/rent CSV slices cleared before scrape when scraping is enabled)."
    )
    _run_sold_rented_scrape_for_window(
        window=rolling, run_scrapers=run_scrapers, headless=headless
    )
    build_rent_models()
    validate_monthly_outputs()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        sold_new, rented_new = append_history_window(
            session,
            window_start=rolling.start,
            window_end=rolling.end,
        )
        session.commit()
    print(
        f"History append (new rows only): sold={sold_new:,}, rented={rented_new:,}"
    )

    _run_script(
        "load_to_db.py",
        ["--skip-active"],
        role="DB loader (history/rent/sold analytics; keep active listings untouched)",
    )
    create_monthly_snapshot(folder_name=f"data-{rolling.end:%Y-%m-%d}-rolling")
    print("=== WEEKLY SOLD/RENTED COMPLETE ===")


def run_adhoc_history_window(
    *,
    window: DateWindow,
    run_scrapers: bool,
    headless: bool,
    run_load_db: bool,
) -> None:
    print("=== ADHOC HISTORY WINDOW START ===")
    print(f"Adhoc MLS window {window.start:%Y-%m-%d} .. {window.end:%Y-%m-%d}")
    _run_sold_rented_scrape_for_window(
        window=window,
        run_scrapers=run_scrapers,
        headless=headless,
    )
    build_rent_models()
    validate_monthly_outputs()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        sold_new, rented_new = append_history_window(
            session,
            window_start=window.start,
            window_end=window.end,
        )
        session.commit()
    print(
        f"History append (new rows only): sold={sold_new:,}, rented={rented_new:,}"
    )

    if run_load_db:
        _run_script(
            "load_to_db.py",
            ["--skip-active"],
            role="DB loader (history/rent/sold analytics; keep active listings untouched)",
        )
    else:
        print("Skipped load_to_db.py (--no-load-db).")

    create_monthly_snapshot(
        folder_name=f"data-{window.start:%Y-%m-%d}-to-{window.end:%Y-%m-%d}-adhoc"
    )
    print("=== ADHOC HISTORY WINDOW COMPLETE ===")


def _dispatch_command(args: Namespace) -> None:
    _enforce_scrape_lock(args)
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
    elif args.command == "adhoc-history-window":
        start = _parse_iso_date(args.start, arg_name="--start")
        end = _parse_iso_date(args.end, arg_name="--end")
        if end < start:
            raise ValueError("--end must be >= --start")
        run_adhoc_history_window(
            window=DateWindow(start=start, end=end),
            run_scrapers=not args.no_scrape,
            headless=args.headless,
            run_load_db=not args.no_load_db,
        )
    elif args.command == "daily-active":
        run_daily_active_pipeline_with_geocode(
            run_scraper=args.with_scrape,
            run_geocode=args.with_geocode,
            run_load_db=not args.no_load_db,
            headless=args.headless,
            from_start=args.from_start,
        )
    elif args.command == "validate-monthly":
        validate_monthly_outputs()
    elif args.command == "validate-daily-active":
        validate_daily_active_outputs()
    elif args.command == "load-db":
        _run_script("load_to_db.py", role="DB loader")
    elif args.command == "geocode-active":
        _run_script("geocode_active.py", role="Geocoder")
    else:  # pragma: no cover
        raise ValueError(f"Unknown command: {args.command}")


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
        help="Weekly MLS sold/rented: scrape rolling last 3 calendar months, append new history rows",
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

    adhoc = subparsers.add_parser(
        "adhoc-history-window",
        help="Adhoc sold/rented window: scrape exact date span and append only new history rows",
    )
    adhoc.add_argument(
        "--start",
        required=True,
        help="Window start date (YYYY-MM-DD) for MLS Off-Market timeframe",
    )
    adhoc.add_argument(
        "--end",
        required=True,
        help="Window end date (YYYY-MM-DD) for MLS Off-Market timeframe",
    )
    adhoc.add_argument(
        "--no-scrape",
        action="store_true",
        help="Skip MLS scraping and process existing sold/rent exports already on disk.",
    )
    adhoc.add_argument(
        "--headless",
        action="store_true",
        help="Pass --headless to scraping scripts.",
    )
    adhoc.add_argument(
        "--no-load-db",
        action="store_true",
        help="Skip load_to_db.py (history append still runs).",
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
        help="Geocode active listings after cleaning (before optional DB load).",
    )
    daily.add_argument(
        "--no-load-db",
        action="store_true",
        help="Skip loading cleaned outputs into Postgres after daily active pipeline.",
    )
    daily.add_argument(
        "--headless",
        action="store_true",
        help="Pass --headless to active scraping script.",
    )
    daily.add_argument(
        "--from-start",
        action="store_true",
        help=(
            "With --with-scrape: ignore existing active_export_*.csv bands and re-download from $0 "
            "(full MLS refresh; slower). Omit for normal resume behavior."
        ),
    )

    subparsers.add_parser("validate-monthly", help="Validate monthly outputs only")
    subparsers.add_parser("validate-daily-active", help="Validate daily-active outputs only")
    subparsers.add_parser("load-db", help="Load cleaned/analytics outputs into Postgres")
    subparsers.add_parser("geocode-active", help="Geocode active_clean_latest.csv addresses")

    args = parser.parse_args()

    # Loud hints when scheduled jobs omit scraping—easy to misconfigure prod cron (Git never sees crontab).
    if args.command == "daily-active" and not args.with_scrape:
        print(
            "WARNING: daily-active is running WITHOUT --with-scrape. "
            "Only CSV files already on disk will be combined — no MLS browser login or fresh downloads. "
            "Production schedules should normally use: pipeline.py daily-active --with-scrape --headless",
            file=sys.stderr,
            flush=True,
        )
    if args.command == "weekly-sold-rented" and args.no_scrape:
        print(
            "WARNING: weekly-sold-rented is running WITH --no-scrape. "
            "MLS sold/rent downloads are skipped; existing exports on disk are processed only.",
            file=sys.stderr,
            flush=True,
        )
    if args.command == "adhoc-history-window" and args.no_scrape:
        print(
            "WARNING: adhoc-history-window is running WITH --no-scrape. "
            "MLS sold/rent downloads are skipped; existing exports on disk are processed only.",
            file=sys.stderr,
            flush=True,
        )

    from backend.pipeline_run_log import (
        begin_pipeline_run,
        finish_pipeline_run,
        format_argv_for_log,
    )

    argv_snapshot = format_argv_for_log(args)
    run_id = begin_pipeline_run(args.command, argv_snapshot)
    if run_id is not None:
        print(f"PIPELINE_RUN_LOG_ANCHOR id={run_id} job={args.command}", flush=True)
    exit_code = 0
    detail: dict[str, object] = {}
    try:
        _dispatch_command(args)
    except KeyboardInterrupt:
        exit_code = 130
        detail["error"] = "KeyboardInterrupt"
        raise
    except Exception as exc:
        exit_code = 1
        detail["error"] = repr(exc)
        raise
    finally:
        try:
            from backend.run_metrics import gather_run_metrics

            detail.update(gather_run_metrics(args.command))
        except Exception as mc:  # pragma: no cover - defensive
            detail["metrics_collection_error"] = repr(mc)
        finish_pipeline_run(run_id, exit_code=exit_code, detail=detail)


if __name__ == "__main__":
    main()
