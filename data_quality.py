from pathlib import Path
import pandas as pd


PROJECT_DIR = Path(__file__).parent
COMBINED_DIR = PROJECT_DIR / "combined"
CLEANED_DIR = PROJECT_DIR / "cleaned"
ANALYTICS_DIR = PROJECT_DIR / "analytics"


def _load_rows_cols(path: Path) -> tuple[int, int]:
    df = pd.read_csv(path, low_memory=False)
    return len(df), len(df.columns)


def _assert_file_exists(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required output is missing: {path}")


def validate_monthly_outputs() -> None:
    required = [
        COMBINED_DIR / "sold_master_latest.csv",
        COMBINED_DIR / "rentals_master_latest.csv",
        CLEANED_DIR / "sold_clean_latest.csv",
        CLEANED_DIR / "rentals_clean_latest.csv",
        ANALYTICS_DIR / "rent_by_zip_bedrooms.csv",
        ANALYTICS_DIR / "rent_by_zip_sqft.csv",
    ]
    for path in required:
        _assert_file_exists(path)

    for path in required:
        rows, cols = _load_rows_cols(path)
        if rows <= 0:
            raise ValueError(f"Validation failed: {path.name} has 0 rows")
        if cols <= 0:
            raise ValueError(f"Validation failed: {path.name} has 0 columns")

    rentals_clean = pd.read_csv(
        CLEANED_DIR / "rentals_clean_latest.csv",
        low_memory=False,
        dtype={"zip_code": "string"},
    )
    if "zip_code" in rentals_clean.columns:
        zip_series = rentals_clean["zip_code"].astype("string").str.strip()
        short_numeric = zip_series.str.fullmatch(r"\d{1,4}", na=False).sum()
        if short_numeric > 0:
            raise ValueError(
                f"Validation failed: rentals_clean_latest.csv has {short_numeric} short numeric ZIP values"
            )

    rent_model = pd.read_csv(ANALYTICS_DIR / "rent_by_zip_bedrooms.csv", low_memory=False)
    if len(rent_model) < 100:
        raise ValueError(
            f"Validation failed: rent_by_zip_bedrooms.csv has unexpectedly few rows ({len(rent_model)})"
        )

    print("Monthly data quality checks passed.")


def validate_daily_active_outputs() -> None:
    active_clean = CLEANED_DIR / "active_clean_latest.csv"
    _assert_file_exists(active_clean)
    rows, cols = _load_rows_cols(active_clean)
    if rows <= 0 or cols <= 0:
        raise ValueError("Validation failed: active_clean_latest.csv is empty")

    active_df = pd.read_csv(active_clean, low_memory=False)
    if "status" in active_df.columns:
        statuses = active_df["status"].astype("string").str.upper().dropna()
        if len(statuses) and not statuses.str.contains("ACT", na=False).any():
            print("Warning: active dataset has no obvious ACTIVE statuses.")

    print("Daily active data quality checks passed.")
