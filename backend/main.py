from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

import pandas as pd

from backend.db import Base, engine, get_db
from backend.models import (
    ActiveListing,
    PipelineRun,
    RentByZipBedroom,
    RentByZipSqft,
    RentedListingHistory,
    SoldListingHistory,
)
from backend.nominatim_geocode import geocode_one_listing, load_query_cache, save_query_cache
from backend.schemas import (
    ActiveListingOut,
    GeocodeBatchIn,
    GeocodeUpdateOut,
    OpsSummaryRow,
    PipelineRunOut,
    RentedListingHistoryOut,
    RentByZipBedroomOut,
    RentByZipSqftOut,
    SoldListingHistoryOut,
)
from backend.zip_normalize import normalize_us_zip_5, zip_column_eq_normalized


app = FastAPI(title="MLS Analytics API", version="0.1.0")
PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
SOLD_CLEAN_PATH = PROJECT_DIR / "cleaned" / "sold_clean_latest.csv"

_sold_df_cache: pd.DataFrame | None = None


def _load_sold_df() -> pd.DataFrame:
    """Load cached cleaned sold CSV for analytics endpoints."""
    global _sold_df_cache
    if _sold_df_cache is not None:
        return _sold_df_cache
    if not SOLD_CLEAN_PATH.exists():
        raise FileNotFoundError(f"Sold data not found: {SOLD_CLEAN_PATH}")
    df = pd.read_csv(SOLD_CLEAN_PATH, low_memory=False)
    # Normalize key columns we rely on.
    for col in ["sale_price", "bedrooms", "zip_code", "town", "property_type_clean", "settled_date"]:
        if col not in df.columns:
            raise ValueError(f"sold_clean_latest.csv missing required column: {col}")
    # Parse settled_date to datetime for time windows & monthly grouping.
    df["settled_dt"] = pd.to_datetime(df["settled_date"], errors="coerce", utc=True)
    _sold_df_cache = df
    return df


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    # create_all does not add new columns on existing Postgres tables
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(
                text("ALTER TABLE active_listings ADD COLUMN IF NOT EXISTS taxes DOUBLE PRECISION")
            )
            conn.execute(
                text("ALTER TABLE active_listings ADD COLUMN IF NOT EXISTS tax_year DOUBLE PRECISION")
            )


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ops")
def ops_dashboard() -> FileResponse:
    """Operations dashboard (pipeline runs)."""
    path = FRONTEND_DIR / "ops.html"
    if not path.exists():
        return FileResponse(FRONTEND_DIR / "index.html")
    return FileResponse(path)


@app.get("/ops/runs", response_model=list[PipelineRunOut])
def list_pipeline_runs(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PipelineRun]:
    stmt = select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(limit)
    return list(db.execute(stmt).scalars().all())


@app.get("/ops/summary", response_model=list[OpsSummaryRow])
def ops_summary(db: Session = Depends(get_db)) -> list[OpsSummaryRow]:
    """Latest successful finish time per ``job_key`` (scheduled pipeline commands)."""
    rows = list(
        db.execute(
            select(PipelineRun)
            .where(PipelineRun.exit_code == 0)
            .where(PipelineRun.finished_at.isnot(None))
            .order_by(desc(PipelineRun.finished_at))
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    out: list[OpsSummaryRow] = []
    for r in rows:
        if r.job_key in seen:
            continue
        seen.add(r.job_key)
        out.append(
            OpsSummaryRow(
                job_key=r.job_key,
                last_success_at=r.finished_at,
                last_exit_code=r.exit_code,
                run_id=r.id,
            )
        )
    return out


@app.get("/ops/runs/{run_id}", response_model=PipelineRunOut)
def get_pipeline_run(run_id: int, db: Session = Depends(get_db)) -> PipelineRun:
    row = db.get(PipelineRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return row


@app.get("/sold-area-stats")
def sold_area_stats(
    zip_code: str | None = None,
    town: str | None = None,
    min_beds: float | None = None,
    max_beds: float | None = None,
    property_type: str | None = Query(
        default=None,
        description="Optional cleaned property type filter, e.g. SF, CONDO, MF.",
    ),
    months_back: int = Query(default=12, ge=1, le=60),
    db: Session = Depends(get_db),
) -> dict:
    """
    Area-level sold stats for homebuyers: typical prices, ranges, and recent trends.

    Uses cleaned sold CSV, filtered by ZIP / town / bedrooms / property type, and
    looks back roughly ``months_back`` months based on settled date.
    """
    from backend.zip_normalize import normalize_us_zip_5  # local import to avoid cycles

    try:
        df = _load_sold_df()
    except Exception as exc:  # pragma: no cover - simple error surface
        return {
            "summary": None,
            "trend_by_month": [],
            "current_active_snapshot": None,
            "error": str(exc),
        }

    df_f = df.copy()

    # Time window: approximate months_back by 30-day chunks.
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30 * months_back)
    if "settled_dt" in df_f.columns:
        df_f = df_f[df_f["settled_dt"] >= cutoff]

    # Only rows with a real sale price and marked as sold dataset_type.
    df_f = df_f[
        (pd.to_numeric(df_f["sale_price"], errors="coerce") > 0)
        & (df_f.get("dataset_type") == "sold")
    ]

    # Location filters.
    if zip_code:
        z = normalize_us_zip_5(zip_code)
        if z:
            df_f = df_f[df_f["zip_code"].astype(str).str.zfill(5) == z]
    if town:
        t = town.strip().lower()
        df_f = df_f[df_f["town"].astype(str).str.lower() == t]

    # Beds filter.
    beds = pd.to_numeric(df_f["bedrooms"], errors="coerce")
    if min_beds is not None:
        df_f = df_f[beds >= float(min_beds)]
        beds = pd.to_numeric(df_f["bedrooms"], errors="coerce")
    if max_beds is not None:
        df_f = df_f[beds <= float(max_beds)]

    # Property type (cleaned from pipeline).
    if property_type:
        pt = property_type.strip().upper()
        df_f = df_f[df_f["property_type_clean"].astype(str).str.upper() == pt]

    num_sales = int(len(df_f))
    if num_sales == 0:
        return {
            "summary": {
                "num_sales": 0,
                "price_median": None,
                "price_p25": None,
                "price_p75": None,
                "price_sqft_median": None,
            },
            "trend_by_month": [],
            "current_active_snapshot": None,
        }

    prices = pd.to_numeric(df_f["sale_price"], errors="coerce")
    sqft = pd.to_numeric(df_f.get("square_feet"), errors="coerce")

    price_median = float(prices.median())
    price_p25 = float(prices.quantile(0.25))
    price_p75 = float(prices.quantile(0.75))
    price_sqft_median = None
    if not sqft.isna().all():
        pps = prices / sqft.replace(0, pd.NA)
        pps = pps.replace([pd.NA, pd.NaT], pd.NA).dropna()
        if not pps.empty:
            price_sqft_median = float(pps.median())

    # Monthly trend: median price and count by YYYY-MM.
    if "settled_dt" in df_f.columns:
        df_f = df_f.dropna(subset=["settled_dt"])
        df_f["month"] = df_f["settled_dt"].dt.to_period("M").astype(str)
    else:
        df_f["month"] = df_f["sale_year"].astype(int).astype(str)
    grp = df_f.groupby("month")
    trend = []
    for month, g in grp:
        gp = pd.to_numeric(g["sale_price"], errors="coerce")
        median_price = float(gp.median()) if not gp.empty else None
        trend.append(
            {
                "month": month,
                "median_price": median_price,
                "num_sales": int(len(g)),
            }
        )
    trend = sorted(trend, key=lambda r: r["month"])

    # Optional: current active listings snapshot in same area/filters.
    from backend.models import ActiveListing
    from backend.zip_normalize import zip_column_eq_normalized

    stmt = select(ActiveListing)
    if zip_code:
        z = normalize_us_zip_5(zip_code)
        if z:
            stmt = stmt.where(zip_column_eq_normalized(ActiveListing.zip_code, z))
    if town:
        stmt = stmt.where(func.lower(ActiveListing.town) == town.strip().lower())
    if min_beds is not None:
        stmt = stmt.where(ActiveListing.bedrooms >= float(min_beds))
    if max_beds is not None:
        stmt = stmt.where(ActiveListing.bedrooms <= float(max_beds))
    if property_type:
        pt = property_type.strip().upper()
        stmt = stmt.where(func.upper(ActiveListing.property_type) == pt)

    active_rows = list(db.execute(stmt).scalars().all())
    if active_rows:
        active_prices = [r.list_price for r in active_rows if r.list_price is not None]
        if active_prices:
            active_avg = float(sum(active_prices) / len(active_prices))
            active_median = float(sorted(active_prices)[len(active_prices) // 2])
            active_vs_sold_pct = None
            if price_median and price_median > 0:
                active_vs_sold_pct = float((active_median / price_median - 1) * 100)
        else:
            active_avg = active_median = active_vs_sold_pct = None
        active_snapshot = {
            "num_active": len(active_rows),
            "active_price_avg": active_avg,
            "active_price_median": active_median,
            "active_vs_sold_pct": active_vs_sold_pct,
        }
    else:
        active_snapshot = None

    return {
        "summary": {
            "num_sales": num_sales,
            "price_median": price_median,
            "price_p25": price_p25,
            "price_p75": price_p75,
            "price_sqft_median": price_sqft_median,
        },
        "trend_by_month": trend,
        "current_active_snapshot": active_snapshot,
    }


@app.get("/sold-comps")
def sold_comps(
    mls_id: str | None = None,
    months_back: int = 12,
    db: Session = Depends(get_db),
) -> dict:
    """
    Find recent similar sales ("comps") for a specific active listing.

    For now, requires an active MLS ID. Uses:
    - same ZIP
    - bedrooms within ±1
    - square footage within ±30%
    - sales within roughly the last ``months_back`` months
    """
    if not mls_id:
        return {"error": "mls_id is required"}

    # Look up subject listing from active_listings.
    subject = db.get(ActiveListing, mls_id)
    if subject is None:
        return {"error": f"Active listing {mls_id!r} not found.", "subject": None, "summary": None, "comps": []}

    try:
        df = _load_sold_df()
    except Exception as exc:  # pragma: no cover - simple surface
        return {"error": str(exc), "subject": None, "summary": None, "comps": []}

    subj_zip = normalize_us_zip_5(subject.zip_code)
    subj_beds = float(subject.bedrooms) if subject.bedrooms is not None else None
    subj_sqft = float(subject.square_feet) if subject.square_feet is not None else None

    df_f = df.copy()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30 * months_back)
    if "settled_dt" in df_f.columns:
        df_f = df_f[df_f["settled_dt"] >= cutoff]
    df_f = df_f[
        (pd.to_numeric(df_f["sale_price"], errors="coerce") > 0)
        & (df_f.get("dataset_type") == "sold")
    ]

    if subj_zip:
        df_f = df_f[df_f["zip_code"].astype(str).str.zfill(5) == subj_zip]

    beds = pd.to_numeric(df_f["bedrooms"], errors="coerce")
    if subj_beds is not None:
        df_f = df_f[(beds >= subj_beds - 1.0) & (beds <= subj_beds + 1.0)]

    sqft = pd.to_numeric(df_f.get("square_feet"), errors="coerce")
    if subj_sqft is not None and subj_sqft > 0:
        low = subj_sqft * 0.7
        high = subj_sqft * 1.3
        df_f = df_f[(sqft >= low) & (sqft <= high)]

    if df_f.empty:
        return {
            "subject": {
                "mls_id": subject.mls_id,
                "address": subject.full_address or subject.address,
                "zip_code": subj_zip,
                "bedrooms": subj_beds,
                "total_baths": subject.total_baths,
                "square_feet": subj_sqft,
                "list_price": subject.list_price,
            },
            "summary": {
                "num_comps": 0,
                "median_price": None,
                "price_p25": None,
                "price_p75": None,
                "median_ppsf": None,
                "list_vs_median_pct": None,
            },
            "comps": [],
        }

    prices = pd.to_numeric(df_f["sale_price"], errors="coerce")
    sqft = pd.to_numeric(df_f.get("square_feet"), errors="coerce")
    price_median = float(prices.median())
    price_p25 = float(prices.quantile(0.25))
    price_p75 = float(prices.quantile(0.75))

    median_ppsf = None
    if not sqft.isna().all():
        pps = prices / sqft.replace(0, pd.NA)
        pps = pps.replace([pd.NA, pd.NaT], pd.NA).dropna()
        if not pps.empty:
            median_ppsf = float(pps.median())

    list_vs_median_pct = None
    if subject.list_price and price_median:
        try:
            list_vs_median_pct = float((subject.list_price / price_median - 1) * 100)
        except ZeroDivisionError:
            list_vs_median_pct = None

    # Build a simple distance metric to pick closest ~10 comps.
    def _score(row) -> float:
        score = 0.0
        sp = float(row.get("sale_price") or 0)
        if subject.list_price:
            score += abs(sp - subject.list_price) / max(subject.list_price, 1)
        rbeds = float(row.get("bedrooms") or 0)
        if subj_beds is not None:
            score += 0.2 * abs(rbeds - subj_beds)
        rsqft = float(row.get("square_feet") or 0)
        if subj_sqft is not None and subj_sqft > 0 and rsqft > 0:
            score += abs(rsqft - subj_sqft) / subj_sqft
        return score

    df_f = df_f.copy()
    df_f["_score"] = df_f.apply(_score, axis=1)
    df_f = df_f.sort_values("_score").head(10)

    comps = []
    for _, r in df_f.iterrows():
        comps.append(
            {
                "full_address": r.get("full_address") or r.get("address"),
                "sale_price": float(r.get("sale_price") or 0),
                "bedrooms": None if pd.isna(r.get("bedrooms")) else float(r.get("bedrooms")),
                "total_baths": None if pd.isna(r.get("total_baths")) else float(r.get("total_baths")),
                "square_feet": None if pd.isna(r.get("square_feet")) else float(r.get("square_feet")),
                "settled_date": r.get("settled_date"),
            }
        )

    return {
        "subject": {
            "mls_id": subject.mls_id,
            "address": subject.full_address or subject.address,
            "zip_code": subj_zip,
            "bedrooms": subj_beds,
            "total_baths": subject.total_baths,
            "square_feet": subj_sqft,
            "list_price": subject.list_price,
        },
        "summary": {
            "num_comps": int(len(df_f)),
            "median_price": price_median,
            "price_p25": price_p25,
            "price_p75": price_p75,
            "median_ppsf": median_ppsf,
            "list_vs_median_pct": list_vs_median_pct,
        },
        "comps": comps,
    }


@app.get("/active-listings", response_model=list[ActiveListingOut])
def list_active_listings(
    zip_code: str | None = None,
    town: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_beds: float | None = None,
    max_beds: float | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[ActiveListing]:
    stmt = select(ActiveListing)

    zip_norm = normalize_us_zip_5(zip_code)
    if zip_norm:
        stmt = stmt.where(zip_column_eq_normalized(ActiveListing.zip_code, zip_norm))
    if town:
        stmt = stmt.where(func.lower(ActiveListing.town) == town.lower())
    if min_price is not None:
        stmt = stmt.where(ActiveListing.list_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(ActiveListing.list_price <= max_price)
    if min_beds is not None:
        stmt = stmt.where(ActiveListing.bedrooms >= min_beds)
    if max_beds is not None:
        stmt = stmt.where(ActiveListing.bedrooms <= max_beds)

    stmt = stmt.order_by(ActiveListing.list_price.asc().nulls_last()).limit(limit)
    return list(db.execute(stmt).scalars().all())


@app.post("/geocode/active-listings", response_model=list[GeocodeUpdateOut])
def geocode_active_listings_batch(
    body: GeocodeBatchIn,
    db: Session = Depends(get_db),
) -> list[GeocodeUpdateOut]:
    """
    Fill missing lat/lon for the given MLS IDs (OpenStreetMap Nominatim).
    Persists coordinates to the DB and uses the same on-disk cache as geocode_active.py.
    """
    cache = load_query_cache()
    updates: list[GeocodeUpdateOut] = []
    for mls_id in body.mls_ids:
        row = db.get(ActiveListing, mls_id)
        if row is None:
            continue
        if row.latitude is not None and row.longitude is not None:
            continue
        found = geocode_one_listing(
            full_address=row.full_address,
            address=row.address,
            town=row.town,
            state=row.state,
            zip_code=row.zip_code,
            cache=cache,
            rate_limit_seconds=1.05,
        )
        if found is None:
            continue
        row.latitude, row.longitude = found[0], found[1]
        updates.append(
            GeocodeUpdateOut(mls_id=row.mls_id, latitude=found[0], longitude=found[1])
        )
    db.commit()
    save_query_cache(cache)
    return updates


@app.get("/map/active-points")
def active_points(
    zip_code: str | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(
        ActiveListing.mls_id,
        ActiveListing.full_address,
        ActiveListing.zip_code,
        ActiveListing.list_price,
        ActiveListing.bedrooms,
        ActiveListing.total_baths,
        ActiveListing.square_feet,
        ActiveListing.latitude,
        ActiveListing.longitude,
    )
    zip_norm = normalize_us_zip_5(zip_code)
    if zip_norm:
        stmt = stmt.where(zip_column_eq_normalized(ActiveListing.zip_code, zip_norm))
    stmt = stmt.limit(limit)

    rows = db.execute(stmt).all()
    return [
        {
            "mls_id": r.mls_id,
            "full_address": r.full_address,
            "zip_code": r.zip_code,
            "list_price": r.list_price,
            "bedrooms": r.bedrooms,
            "total_baths": r.total_baths,
            "square_feet": r.square_feet,
            "latitude": r.latitude,
            "longitude": r.longitude,
        }
        for r in rows
    ]


@app.get("/analytics/rent-by-zip-bedroom", response_model=list[RentByZipBedroomOut])
def rent_by_zip_bedroom(
    zip_code: str | None = None,
    bedrooms: float | None = None,
    min_beds: float | None = None,
    max_beds: float | None = None,
    db: Session = Depends(get_db),
) -> list[RentByZipBedroom]:
    stmt = select(RentByZipBedroom)
    zip_norm = normalize_us_zip_5(zip_code)
    if zip_norm:
        stmt = stmt.where(zip_column_eq_normalized(RentByZipBedroom.zip_code, zip_norm))
    if bedrooms is not None:
        stmt = stmt.where(RentByZipBedroom.bedrooms == bedrooms)
    else:
        if min_beds is not None:
            stmt = stmt.where(RentByZipBedroom.bedrooms >= min_beds)
        if max_beds is not None:
            stmt = stmt.where(RentByZipBedroom.bedrooms <= max_beds)
    stmt = stmt.order_by(RentByZipBedroom.zip_code, RentByZipBedroom.bedrooms)
    return list(db.execute(stmt).scalars().all())


@app.get("/analytics/rent-by-zip-sqft", response_model=list[RentByZipSqftOut])
def rent_by_zip_sqft(
    zip_code: str | None = None,
    db: Session = Depends(get_db),
) -> list[RentByZipSqft]:
    stmt = select(RentByZipSqft)
    zip_norm = normalize_us_zip_5(zip_code)
    if zip_norm:
        stmt = stmt.where(zip_column_eq_normalized(RentByZipSqft.zip_code, zip_norm))
    stmt = stmt.order_by(RentByZipSqft.zip_code)
    return list(db.execute(stmt).scalars().all())


@app.get("/history/sold", response_model=list[SoldListingHistoryOut])
def sold_history(
    start_date: str | None = None,
    end_date: str | None = None,
    zip_code: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[SoldListingHistory]:
    stmt = select(SoldListingHistory)
    if start_date:
        stmt = stmt.where(SoldListingHistory.event_date >= pd.to_datetime(start_date).date())
    if end_date:
        stmt = stmt.where(SoldListingHistory.event_date <= pd.to_datetime(end_date).date())
    zip_norm = normalize_us_zip_5(zip_code)
    if zip_norm:
        stmt = stmt.where(zip_column_eq_normalized(SoldListingHistory.zip_code, zip_norm))
    stmt = stmt.order_by(SoldListingHistory.event_date.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


@app.get("/history/rented", response_model=list[RentedListingHistoryOut])
def rented_history(
    start_date: str | None = None,
    end_date: str | None = None,
    zip_code: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[RentedListingHistory]:
    stmt = select(RentedListingHistory)
    if start_date:
        stmt = stmt.where(RentedListingHistory.event_date >= pd.to_datetime(start_date).date())
    if end_date:
        stmt = stmt.where(RentedListingHistory.event_date <= pd.to_datetime(end_date).date())
    zip_norm = normalize_us_zip_5(zip_code)
    if zip_norm:
        stmt = stmt.where(zip_column_eq_normalized(RentedListingHistory.zip_code, zip_norm))
    stmt = stmt.order_by(RentedListingHistory.event_date.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())
