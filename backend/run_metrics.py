"""Collect lightweight row/file counts after a pipeline run (for ops dashboard)."""

from __future__ import annotations

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
COMBINED_DIR = PROJECT_DIR / "combined"
CLEANED_DIR = PROJECT_DIR / "cleaned"
ANALYTICS_DIR = PROJECT_DIR / "analytics"
DOWNLOADS_ACTIVE_DIR = PROJECT_DIR / "downloads" / "active"
DOWNLOADS_DIR = PROJECT_DIR / "downloads"
RENTALS_DOWNLOADS_DIR = PROJECT_DIR / "downloads" / "rentals"


def _count_csv_data_rows(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as fh:
            n = sum(1 for _ in fh)
        return max(0, n - 1)
    except OSError:
        return None


def _count_glob(pattern_dir: Path, pattern: str) -> int | None:
    if not pattern_dir.is_dir():
        return None
    return len(list(pattern_dir.glob(pattern)))


def _add_database_counts(m: dict[str, object]) -> None:
    """Attach DB row counts when Postgres is reachable."""
    try:
        from sqlalchemy import func, select

        from backend.db import SessionLocal
        from backend.models import ActiveListing, SoldAnalyticsSnapshot

        with SessionLocal() as session:
            n_act = session.execute(select(func.count()).select_from(ActiveListing)).scalar_one()
            m["active_listings_in_database"] = int(n_act)
            n_sold = session.execute(select(func.count()).select_from(SoldAnalyticsSnapshot)).scalar_one()
            m["sold_analytics_snapshot_rows"] = int(n_sold)
    except Exception:
        m["database_metrics_note"] = "Could not query database row counts (database unavailable?)"


def gather_run_metrics(job_key: str) -> dict[str, object]:
    """Best-effort counts after a run; missing files yield omitted keys."""
    m: dict[str, object] = {}

    if job_key == "daily-active":
        m["active_listings_combined_rows"] = _count_csv_data_rows(COMBINED_DIR / "active_latest.csv")
        m["active_listings_after_cleaning"] = _count_csv_data_rows(CLEANED_DIR / "active_clean_latest.csv")
        n_files = _count_glob(DOWNLOADS_ACTIVE_DIR, "active_export_*.csv")
        if n_files is not None:
            m["raw_mls_export_files"] = n_files

    elif job_key in ("weekly-sold-rented", "monthly", "validate-monthly"):
        ns = _count_glob(DOWNLOADS_DIR, "mls_export_*.csv")
        nr = _count_glob(RENTALS_DOWNLOADS_DIR, "rentals_export_*.csv")
        if ns is not None:
            m["sold_export_files"] = ns
        if nr is not None:
            m["rentals_export_files"] = nr
        m["sold_rows_cleaned"] = _count_csv_data_rows(CLEANED_DIR / "sold_clean_latest.csv")
        m["rentals_rows_cleaned"] = _count_csv_data_rows(CLEANED_DIR / "rentals_clean_latest.csv")
        m["sold_rows_combined"] = _count_csv_data_rows(COMBINED_DIR / "sold_master_latest.csv")
        m["rentals_rows_combined"] = _count_csv_data_rows(COMBINED_DIR / "rentals_master_latest.csv")
        m["rent_zip_bedroom_buckets"] = _count_csv_data_rows(ANALYTICS_DIR / "rent_by_zip_bedrooms.csv")
        m["rent_zip_sqft_buckets"] = _count_csv_data_rows(ANALYTICS_DIR / "rent_by_zip_sqft.csv")

    elif job_key == "validate-daily-active":
        m["active_listings_after_cleaning"] = _count_csv_data_rows(CLEANED_DIR / "active_clean_latest.csv")

    if job_key in ("daily-active", "load-db", "weekly-sold-rented"):
        _add_database_counts(m)

    return {k: v for k, v in m.items() if v is not None}
