from datetime import datetime
from pathlib import Path
import shutil


PROJECT_DIR = Path(__file__).parent
COMBINED_DIR = PROJECT_DIR / "combined"
CLEANED_DIR = PROJECT_DIR / "cleaned"
ANALYTICS_DIR = PROJECT_DIR / "analytics"
HISTORY_DIR = PROJECT_DIR / "history"


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def create_monthly_snapshot(folder_name: str | None = None) -> Path:
    """
    Copy monthly pipeline artifacts under ``history/monthly/<folder_name>/``.

    ``folder_name`` defaults to today's calendar date (``YYYY-MM-DD``).
    For memorialized windows, pass ``data-YYYY-MM`` so folders match the data month.
    Weekly hot-window snapshots use ``data-YYYY-MM-rolling``.
    """
    if folder_name is None:
        folder_name = datetime.now().strftime("%Y-%m-%d")

    target_dir = HISTORY_DIR / "monthly" / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        COMBINED_DIR / "sold_master_latest.csv",
        COMBINED_DIR / "rentals_master_latest.csv",
        CLEANED_DIR / "sold_clean_latest.csv",
        CLEANED_DIR / "rentals_clean_latest.csv",
        ANALYTICS_DIR / "rent_by_zip_bedrooms.csv",
        ANALYTICS_DIR / "rent_by_zip_sqft.csv",
    ]

    copied = 0
    for src in files_to_copy:
        if _copy_if_exists(src, target_dir / src.name):
            copied += 1

    print(f"Monthly snapshot saved to {target_dir} ({copied} files copied)")
    return target_dir


def create_daily_active_snapshot(snapshot_date: str | None = None) -> Path:
    if snapshot_date is None:
        snapshot_date = datetime.now().strftime("%Y-%m-%d")

    target_dir = HISTORY_DIR / "daily_active" / snapshot_date
    target_dir.mkdir(parents=True, exist_ok=True)

    files_to_copy = [
        COMBINED_DIR / "active_latest.csv",
        CLEANED_DIR / "active_clean_latest.csv",
    ]

    copied = 0
    for src in files_to_copy:
        if _copy_if_exists(src, target_dir / src.name):
            copied += 1

    print(f"Daily active snapshot saved to {target_dir} ({copied} files copied)")
    return target_dir
