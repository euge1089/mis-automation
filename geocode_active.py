from __future__ import annotations

from pathlib import Path
import time

import pandas as pd

from backend.nominatim_geocode import (
    address_query_candidates,
    load_query_cache,
    nominatim_lookup,
    save_query_cache,
)

PROJECT_DIR = Path(__file__).parent
CLEANED_FILE = PROJECT_DIR / "cleaned" / "active_clean_latest.csv"


def _row_field(row: pd.Series, key: str) -> str | None:
    v = row.get(key)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _address_candidates_for_row(row: pd.Series) -> list[str]:
    return address_query_candidates(
        _row_field(row, "full_address"),
        _row_field(row, "address"),
        _row_field(row, "town"),
        _row_field(row, "state"),
        _row_field(row, "zip_code"),
    )


def geocode_active_listings(rate_limit_seconds: float = 1.0) -> Path:
    if not CLEANED_FILE.exists():
        raise FileNotFoundError(f"Missing cleaned active file: {CLEANED_FILE}")

    df = pd.read_csv(CLEANED_FILE, low_memory=False)
    if "latitude" not in df.columns:
        df["latitude"] = pd.NA
    if "longitude" not in df.columns:
        df["longitude"] = pd.NA

    cache = load_query_cache()
    geocoded_count = 0
    miss_count = 0

    total_rows = len(df)
    print(f"Starting geocode_active_listings for {total_rows:,} active rows…")
    progress_step = max(1, total_rows // 10)  # ~10% chunks

    for idx, row in df.iterrows():
        if pd.notna(df.at[idx, "latitude"]) and pd.notna(df.at[idx, "longitude"]):
            continue

        found = None
        for candidate in _address_candidates_for_row(row):
            if candidate in cache:
                found = cache[candidate]
            else:
                found = nominatim_lookup(candidate)
                cache[candidate] = found
                time.sleep(rate_limit_seconds)

            if found is not None:
                break

        if found is None:
            miss_count += 1
            continue

        df.at[idx, "latitude"] = found[0]
        df.at[idx, "longitude"] = found[1]
        geocoded_count += 1

        # Simple progress log every ~10% of dataframe, regardless of success/failure.
        if (idx + 1) % progress_step == 0 or idx + 1 == total_rows:
            print(
                f"Geocoding progress: {idx + 1:,}/{total_rows:,} rows "
                f"({geocoded_count:,} with coordinates, {miss_count:,} misses so far)…"
            )

    df.to_csv(CLEANED_FILE, index=False)
    save_query_cache(cache)
    print(f"Geocoding complete. Added coordinates for {geocoded_count:,} rows. Misses: {miss_count:,}")
    print(f"Updated file: {CLEANED_FILE}")
    return CLEANED_FILE


def main() -> None:
    geocode_active_listings()


if __name__ == "__main__":
    main()
