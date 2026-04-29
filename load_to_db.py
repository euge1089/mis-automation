from __future__ import annotations

import json
from pathlib import Path
from datetime import date, datetime, timezone
import pandas as pd
from sqlalchemy import delete

from backend.db import Base, SessionLocal, engine
from backend.models import (
    ActiveListing,
    RentByZipBedroom,
    RentByZipSqft,
    RentedListingHistory,
    SoldListingHistory,
)
from backend.zip_normalize import normalize_us_zip_5


PROJECT_DIR = Path(__file__).parent
CLEANED_DIR = PROJECT_DIR / "cleaned"
ANALYTICS_DIR = PROJECT_DIR / "analytics"


def _null_if_nan(value):
    if pd.isna(value):
        return None
    return value


def _normalize_zip_cell(value):
    """CSV/Excel often drops leading zeros (02127 → int 2127); store canonical 5-digit text."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, float) and value == int(value):
        value = int(value)
    return normalize_us_zip_5(str(value))


def _to_python_scalar(value):
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return value.item()  # numpy scalar
    except Exception:
        return value


def _coerce_event_date(df: pd.DataFrame, *, dataset: str) -> pd.Series:
    if dataset == "sold":
        candidates = ["settled_date", "off_market_date", "status_date", "list_date"]
    else:
        candidates = ["off_market_date", "status_date", "settled_date", "list_date"]

    result = pd.Series([pd.NaT] * len(df), index=df.index)
    for col in candidates:
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        result = result.fillna(parsed)
    return result.dt.date


def load_active_listings(session) -> int:
    active_file = CLEANED_DIR / "active_clean_latest.csv"
    if not active_file.exists():
        print(f"Skipping active listings load; file not found: {active_file}")
        return 0

    df = pd.read_csv(active_file, low_memory=False)
    required = ["mls_id"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"active_clean_latest.csv missing required columns: {missing}")

    keep_cols = [
        "mls_id",
        "status",
        "property_type",
        "address",
        "town",
        "state",
        "zip_code",
        "bedrooms",
        "total_baths",
        "square_feet",
        "list_price",
        "taxes",
        "tax_year",
        "lot_size",
        "year_built",
        "latitude",
        "longitude",
        "county",
        "neighborhood",
        "full_address",
    ]
    for col in keep_cols:
        if col not in df.columns:
            df[col] = None

    df = df[keep_cols].dropna(subset=["mls_id"]).copy()
    df["mls_id"] = df["mls_id"].astype(str).str.strip()
    df = df[df["mls_id"] != ""]

    session.execute(delete(ActiveListing))
    rows = [
        ActiveListing(
            mls_id=str(row["mls_id"]),
            status=_null_if_nan(row["status"]),
            property_type=_null_if_nan(row["property_type"]),
            address=_null_if_nan(row["address"]),
            town=_null_if_nan(row["town"]),
            state=_null_if_nan(row["state"]),
            zip_code=_normalize_zip_cell(row["zip_code"]),
            bedrooms=_null_if_nan(row["bedrooms"]),
            total_baths=_null_if_nan(row["total_baths"]),
            square_feet=_null_if_nan(row["square_feet"]),
            list_price=_null_if_nan(row["list_price"]),
            taxes=_null_if_nan(row["taxes"]),
            tax_year=_null_if_nan(row["tax_year"]),
            lot_size=_null_if_nan(row["lot_size"]),
            year_built=_null_if_nan(row["year_built"]),
            latitude=_null_if_nan(row["latitude"]),
            longitude=_null_if_nan(row["longitude"]),
            county=_null_if_nan(row["county"]),
            neighborhood=_null_if_nan(row["neighborhood"]),
            full_address=_null_if_nan(row["full_address"]),
        )
        for _, row in df.iterrows()
    ]
    session.bulk_save_objects(rows)
    return len(rows)


def load_rent_analytics(session) -> int:
    rent_file = ANALYTICS_DIR / "rent_by_zip_bedrooms.csv"
    if not rent_file.exists():
        raise FileNotFoundError(f"Missing rent model file: {rent_file}")

    df = pd.read_csv(rent_file, low_memory=False, dtype={"zip_code": "string"})
    required = ["zip_code", "bedrooms"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"rent_by_zip_bedrooms.csv missing required columns: {missing}")

    session.execute(delete(RentByZipBedroom))
    rows = []
    for _, row in df.iterrows():
        zip_code = _normalize_zip_cell(row.get("zip_code"))
        bedrooms = _null_if_nan(row.get("bedrooms"))
        if zip_code is None or bedrooms is None:
            continue
        rows.append(
            RentByZipBedroom(
                zip_code=zip_code,
                bedrooms=float(bedrooms),
                sample_size=_null_if_nan(row.get("sample_size")),
                avg_rent=_null_if_nan(row.get("avg_rent")),
                median_rent=_null_if_nan(row.get("median_rent")),
                min_rent=_null_if_nan(row.get("min_rent")),
                max_rent=_null_if_nan(row.get("max_rent")),
                avg_sqft=_null_if_nan(row.get("avg_sqft")),
                median_sqft=_null_if_nan(row.get("median_sqft")),
                avg_rent_per_sqft=_null_if_nan(row.get("avg_rent_per_sqft")),
                median_rent_per_sqft=_null_if_nan(row.get("median_rent_per_sqft")),
                towns_seen=_null_if_nan(row.get("towns_seen")),
                confidence=_null_if_nan(row.get("confidence")),
            )
        )

    session.bulk_save_objects(rows)
    return len(rows)


def load_rent_sqft_analytics(session) -> int:
    rent_sqft_file = ANALYTICS_DIR / "rent_by_zip_sqft.csv"
    if not rent_sqft_file.exists():
        raise FileNotFoundError(f"Missing rent sqft model file: {rent_sqft_file}")

    df = pd.read_csv(rent_sqft_file, low_memory=False, dtype={"zip_code": "string"})
    required = ["zip_code"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"rent_by_zip_sqft.csv missing required columns: {missing}")

    session.execute(delete(RentByZipSqft))
    rows = []
    for _, row in df.iterrows():
        zip_code = _normalize_zip_cell(row.get("zip_code"))
        if zip_code is None:
            continue
        rows.append(
            RentByZipSqft(
                zip_code=zip_code,
                sample_size=_null_if_nan(row.get("sample_size")),
                avg_rent=_null_if_nan(row.get("avg_rent")),
                median_rent=_null_if_nan(row.get("median_rent")),
                avg_sqft=_null_if_nan(row.get("avg_sqft")),
                median_sqft=_null_if_nan(row.get("median_sqft")),
                avg_rent_per_sqft=_null_if_nan(row.get("avg_rent_per_sqft")),
                median_rent_per_sqft=_null_if_nan(row.get("median_rent_per_sqft")),
                towns_seen=_null_if_nan(row.get("towns_seen")),
                confidence=_null_if_nan(row.get("confidence")),
            )
        )

    session.bulk_save_objects(rows)
    return len(rows)


def _load_cleaned_for_history(dataset: str) -> pd.DataFrame:
    if dataset == "sold":
        file_path = CLEANED_DIR / "sold_clean_latest.csv"
    else:
        file_path = CLEANED_DIR / "rentals_clean_latest.csv"
    if not file_path.exists():
        raise FileNotFoundError(f"Missing cleaned file for memorialization: {file_path}")
    return pd.read_csv(file_path, low_memory=False)


def memorialize_history_window(
    session,
    *,
    window_start: date,
    window_end: date,
    as_of: datetime | None = None,
) -> tuple[int, int]:
    """
    Persist sold/rented transactional records for a closed window.
    Existing rows in the same window are replaced to allow corrections.
    """
    if window_end < window_start:
        raise ValueError("window_end must be >= window_start")

    memorialized_at = as_of or datetime.now(timezone.utc)

    sold_df = _load_cleaned_for_history("sold")
    sold_df["event_date"] = _coerce_event_date(sold_df, dataset="sold")
    sold_df = sold_df[
        sold_df["event_date"].notna()
        & (sold_df["event_date"] >= window_start)
        & (sold_df["event_date"] <= window_end)
    ].copy()

    rentals_df = _load_cleaned_for_history("rentals")
    rentals_df["event_date"] = _coerce_event_date(rentals_df, dataset="rentals")
    rentals_df = rentals_df[
        rentals_df["event_date"].notna()
        & (rentals_df["event_date"] >= window_start)
        & (rentals_df["event_date"] <= window_end)
    ].copy()

    session.execute(
        delete(SoldListingHistory).where(
            SoldListingHistory.event_date >= window_start,
            SoldListingHistory.event_date <= window_end,
        )
    )
    session.execute(
        delete(RentedListingHistory).where(
            RentedListingHistory.event_date >= window_start,
            RentedListingHistory.event_date <= window_end,
        )
    )

    sold_rows = []
    for _, row in sold_df.iterrows():
        event_date = row.get("event_date")
        mls_id = row.get("mls_id")
        if event_date is None or pd.isna(event_date) or pd.isna(mls_id):
            continue
        payload = {
            col: _to_python_scalar(val)
            for col, val in row.items()
            if col != "event_date"
        }
        sold_rows.append(
            SoldListingHistory(
                mls_id=str(mls_id).strip(),
                event_date=event_date,
                status=_null_if_nan(row.get("status")),
                property_type=_null_if_nan(row.get("property_type_clean") or row.get("property_type")),
                town=_null_if_nan(row.get("town")),
                zip_code=_normalize_zip_cell(row.get("zip_code")),
                sale_price=_null_if_nan(row.get("sale_price")),
                bedrooms=_null_if_nan(row.get("bedrooms")),
                total_baths=_null_if_nan(row.get("total_baths")),
                square_feet=_null_if_nan(row.get("square_feet")),
                source_window_start=window_start,
                source_window_end=window_end,
                memorialized_at=memorialized_at,
                payload_json=json.dumps(payload, default=str),
            )
        )

    rented_rows = []
    for _, row in rentals_df.iterrows():
        event_date = row.get("event_date")
        mls_id = row.get("mls_id")
        if event_date is None or pd.isna(event_date) or pd.isna(mls_id):
            continue
        payload = {
            col: _to_python_scalar(val)
            for col, val in row.items()
            if col != "event_date"
        }
        rented_rows.append(
            RentedListingHistory(
                mls_id=str(mls_id).strip(),
                event_date=event_date,
                status=_null_if_nan(row.get("status")),
                property_type=_null_if_nan(row.get("property_type_clean") or row.get("property_type")),
                town=_null_if_nan(row.get("town")),
                zip_code=_normalize_zip_cell(row.get("zip_code")),
                rent_price=_null_if_nan(row.get("rent_price") or row.get("list_price")),
                bedrooms=_null_if_nan(row.get("bedrooms")),
                total_baths=_null_if_nan(row.get("total_baths")),
                square_feet=_null_if_nan(row.get("square_feet")),
                source_window_start=window_start,
                source_window_end=window_end,
                memorialized_at=memorialized_at,
                payload_json=json.dumps(payload, default=str),
            )
        )

    if sold_rows:
        session.bulk_save_objects(sold_rows)
    if rented_rows:
        session.bulk_save_objects(rented_rows)
    return len(sold_rows), len(rented_rows)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        active_count = load_active_listings(session)
        rent_count = load_rent_analytics(session)
        rent_sqft_count = load_rent_sqft_analytics(session)
        session.commit()

    print(f"Loaded active listings: {active_count:,}")
    print(f"Loaded rent-by-zip-bedroom rows: {rent_count:,}")
    print(f"Loaded rent-by-zip-sqft rows: {rent_sqft_count:,}")


if __name__ == "__main__":
    main()
