"""Aggregate rental benchmarks from ``rented_listing_history`` for rolling windows."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import RentedListingHistory
from backend.schemas import RentByZipBedroomOut
from backend.zip_normalize import normalize_us_zip_5, zip_column_eq_normalized


def _confidence_label(n: int) -> str:
    if n >= 20:
        return "High"
    if n >= 8:
        return "Medium"
    if n >= 1:
        return "Low"
    return "None"


def aggregate_rent_by_zip_bedroom_from_history(
    db: Session,
    *,
    zip_code: str | None,
    bedrooms: float | None,
    min_beds: float | None,
    max_beds: float | None,
    months_back: int,
) -> list[RentByZipBedroomOut]:
    """
    Build ZIP × bedroom rent buckets from memorialized rental history within ``months_back``
    (approximated as 30-day months from today).
    """
    zip_norm = normalize_us_zip_5(zip_code or "")
    cutoff = date.today() - timedelta(days=30 * months_back)

    stmt = select(RentedListingHistory).where(RentedListingHistory.event_date >= cutoff)
    if zip_norm:
        stmt = stmt.where(zip_column_eq_normalized(RentedListingHistory.zip_code, zip_norm))
    if bedrooms is not None:
        stmt = stmt.where(RentedListingHistory.bedrooms == bedrooms)
    else:
        if min_beds is not None:
            stmt = stmt.where(RentedListingHistory.bedrooms >= min_beds)
        if max_beds is not None:
            stmt = stmt.where(RentedListingHistory.bedrooms <= max_beds)

    rows = list(db.execute(stmt).scalars().all())
    if not rows:
        return []

    rec = []
    for r in rows:
        rp = r.rent_price
        if rp is None or rp <= 0:
            continue
        z = normalize_us_zip_5(r.zip_code or "") or (r.zip_code or "").strip()
        rec.append(
            {
                "zip_code": z,
                "bedrooms": float(r.bedrooms) if r.bedrooms is not None else float("nan"),
                "rent_price": float(rp),
                "square_feet": float(r.square_feet) if r.square_feet is not None else None,
                "town": r.town,
            }
        )
    if not rec:
        return []

    df = pd.DataFrame(rec)
    df = df[df["bedrooms"].notna()].copy()
    if df.empty:
        return []
    df["rent_per_sqft"] = df.apply(
        lambda x: (x["rent_price"] / x["square_feet"])
        if x["square_feet"] and x["square_feet"] > 0
        else None,
        axis=1,
    )

    def _towns_seen(s: pd.Series) -> str:
        vals = [str(x) for x in s.dropna().unique() if str(x).strip()]
        return ", ".join(sorted(set(vals))[:5])

    grouped = (
        df.groupby(["zip_code", "bedrooms"], dropna=False)
        .agg(
            sample_size=("rent_price", "count"),
            avg_rent=("rent_price", "mean"),
            median_rent=("rent_price", "median"),
            min_rent=("rent_price", "min"),
            max_rent=("rent_price", "max"),
            avg_sqft=("square_feet", "mean"),
            median_sqft=("square_feet", "median"),
            avg_rent_per_sqft=("rent_per_sqft", "mean"),
            median_rent_per_sqft=("rent_per_sqft", "median"),
            towns_seen=("town", _towns_seen),
        )
        .reset_index()
    )

    grouped["confidence"] = grouped["sample_size"].astype(int).map(_confidence_label)

    for col in [
        "avg_rent",
        "median_rent",
        "min_rent",
        "max_rent",
        "avg_sqft",
        "median_sqft",
        "avg_rent_per_sqft",
        "median_rent_per_sqft",
    ]:
        if col in grouped.columns:
            grouped[col] = grouped[col].round(2)

    grouped = grouped.sort_values(["zip_code", "bedrooms"]).reset_index(drop=True)

    out: list[RentByZipBedroomOut] = []
    for _, row in grouped.iterrows():
        out.append(
            RentByZipBedroomOut(
                zip_code=str(row["zip_code"]),
                bedrooms=float(row["bedrooms"]) if pd.notna(row["bedrooms"]) else 0.0,
                sample_size=int(row["sample_size"]),
                avg_rent=float(row["avg_rent"]) if pd.notna(row["avg_rent"]) else None,
                median_rent=float(row["median_rent"]) if pd.notna(row["median_rent"]) else None,
                min_rent=float(row["min_rent"]) if pd.notna(row["min_rent"]) else None,
                max_rent=float(row["max_rent"]) if pd.notna(row["max_rent"]) else None,
                avg_sqft=float(row["avg_sqft"]) if pd.notna(row["avg_sqft"]) else None,
                median_sqft=float(row["median_sqft"]) if pd.notna(row["median_sqft"]) else None,
                avg_rent_per_sqft=float(row["avg_rent_per_sqft"])
                if pd.notna(row["avg_rent_per_sqft"])
                else None,
                median_rent_per_sqft=float(row["median_rent_per_sqft"])
                if pd.notna(row["median_rent_per_sqft"])
                else None,
                towns_seen=str(row["towns_seen"]) if pd.notna(row["towns_seen"]) else None,
                confidence=str(row["confidence"]) if pd.notna(row["confidence"]) else None,
            )
        )
    return out
