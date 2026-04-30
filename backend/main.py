from __future__ import annotations

import os
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, case, desc, func, inspect, select, text
from sqlalchemy.orm import Session

import pandas as pd

from backend.db import Base, engine, get_db
from backend.models import (
    ActiveListing,
    PipelineRun,
    RentByZipBedroom,
    RentByZipSqft,
    RentedListingHistory,
    SoldAnalyticsSnapshot,
    SoldListingHistory,
)
from backend.finance_provider import mortgage_presets_payload
from backend.nominatim_geocode import geocode_one_listing, load_query_cache, save_query_cache
from backend.ops_alerts import alert_settings, daily_active_drop_status
from backend.ops_catalog import JOB_HELP, help_for
from backend.ops_backup import read_backup_status
from backend.ops_disk import disk_usage_snapshot, extended_host_metrics_if_enabled
from backend.ops_enrichment import build_ops_run_row
from backend.ops_logs import read_log_tail, read_run_log_excerpt
from backend.ops_schedule import build_schedule_rows
from backend.schemas import (
    ActiveListingOut,
    DailyActiveDropStatusOut,
    GeocodeBatchIn,
    GeocodeUpdateOut,
    JobCatalogItemOut,
    OpsActiveListingsFreshnessOut,
    OpsAlertsBundleOut,
    OpsBackupStatusOut,
    OpsDiskOut,
    OpsLogExcerptOut,
    OpsLastSuccessOut,
    OpsOverviewOut,
    OpsRunRowOut,
    OpsRunSort,
    OpsRunStatusFilter,
    OpsScheduleRowOut,
    OpsSummaryRow,
    RentedListingHistoryOut,
    RentByZipBedroomOut,
    RentByZipSqftOut,
    SoldListingHistoryOut,
)
from backend.zip_normalize import normalize_us_zip_5, zip_column_eq_normalized


app = FastAPI(title="MLS Analytics API", version="0.1.0")
PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"


def _last_success_for_job(db: Session, job_key: str) -> OpsLastSuccessOut | None:
    r = (
        db.execute(
            select(PipelineRun)
            .where(PipelineRun.job_key == job_key)
            .where(PipelineRun.exit_code == 0)
            .where(PipelineRun.finished_at.isnot(None))
            .order_by(desc(PipelineRun.finished_at))
            .limit(1)
        )
        .scalars()
        .first()
    )
    if r is None:
        return None
    return OpsLastSuccessOut(finished_at=r.finished_at, run_id=r.id)


def _load_sold_df(db: Session) -> pd.DataFrame:
    """Load sold analytics rows from DB snapshot (refreshed by ``load_to_db.py``)."""
    stmt = select(SoldAnalyticsSnapshot)
    rows = list(db.scalars(stmt).all())
    if not rows:
        raise ValueError(
            "Sold analytics snapshot is empty. Run monthly or weekly-sold-rented, then: python pipeline.py load-db"
        )
    records = []
    for r in rows:
        records.append(
            {
                "mls_id": r.mls_id,
                "settled_date": r.settled_date,
                "sale_price": r.sale_price,
                "bedrooms": r.bedrooms,
                "total_baths": r.total_baths,
                "square_feet": r.square_feet,
                "zip_code": r.zip_code,
                "town": r.town,
                "property_type_clean": r.property_type_clean,
                "dataset_type": r.dataset_type,
                "full_address": r.full_address,
                "address": r.address,
                "sale_year": r.sale_year,
            }
        )
    df = pd.DataFrame(records)
    df["settled_dt"] = pd.to_datetime(df["settled_date"], errors="coerce", utc=True)
    return df


def _require_ops_basic_auth(request: Request) -> None:
    """Optional HTTP Basic auth for ops routes when OPS_BASIC_AUTH_USER/PASSWORD are set."""
    user = os.environ.get("OPS_BASIC_AUTH_USER", "").strip()
    password = os.environ.get("OPS_BASIC_AUTH_PASSWORD", "").strip()
    if not user or not password:
        return
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("basic "):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic realm=ops"},
        )
    try:
        import base64

        payload = base64.b64decode(auth.split(" ", 1)[1].strip()).decode("utf-8")
        u, _, p = payload.partition(":")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Authorization header") from None
    if not (secrets.compare_digest(u, user) and secrets.compare_digest(p, password)):
        raise HTTPException(status_code=401, detail="Invalid credentials")


def require_ops_auth(request: Request) -> None:
    """Dependency: enforce optional Basic auth for ops JSON/HTML routes."""
    _require_ops_basic_auth(request)


@app.on_event("startup")
def startup() -> None:
    # Create only tables that are missing. Blind create_all() can hit rare Postgres
    # catalog edge cases if the DB already has application tables from prior runs.
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        schema = table.schema
        if insp.has_table(table.name, schema=schema):
            continue
        table.create(bind=engine)

    # Table creates above do not add new columns on existing Postgres tables
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


@app.get("/ops", dependencies=[Depends(require_ops_auth)])
def ops_dashboard() -> FileResponse:
    """Operations dashboard (pipeline runs)."""
    path = FRONTEND_DIR / "ops.html"
    if not path.exists():
        return FileResponse(FRONTEND_DIR / "index.html")
    return FileResponse(path)


@app.get("/ops/catalog", response_model=list[JobCatalogItemOut], dependencies=[Depends(require_ops_auth)])
def ops_job_catalog() -> list[JobCatalogItemOut]:
    """Plain-language descriptions of each scheduled pipeline command."""
    return [
        JobCatalogItemOut(
            job_key=key,
            title=h.title,
            one_liner=h.one_liner,
            what_it_does=h.what_it_does,
            success_means=h.success_means,
            schedule_hint=h.schedule_hint,
        )
        for key, h in sorted(JOB_HELP.items(), key=lambda kv: kv[1].title.lower())
    ]


@app.get("/ops/alerts", response_model=OpsAlertsBundleOut, dependencies=[Depends(require_ops_auth)])
def ops_alerts_bundle(db: Session = Depends(get_db)) -> OpsAlertsBundleOut:
    """Alert configuration (no secrets) and derived status (e.g. active listing drop check)."""
    settings = alert_settings()
    threshold = float(settings["active_drop_threshold_pct"])
    drop = daily_active_drop_status(db, threshold)
    return OpsAlertsBundleOut(
        slack_configured=bool(settings["slack_configured"]),
        active_drop_threshold_pct=float(settings["active_drop_threshold_pct"]),
        sold_rent_min_rows=int(settings["sold_rent_min_rows"]),
        alert_blurbs=dict(settings["alert_blurbs"]),
        daily_active_drop=DailyActiveDropStatusOut(**drop),
    )


@app.get("/ops/overview", response_model=OpsOverviewOut, dependencies=[Depends(require_ops_auth)])
def ops_overview(db: Session = Depends(get_db)) -> OpsOverviewOut:
    """Health-at-a-glance: last successful runs and listing count when available."""
    daily = _last_success_for_job(db, "daily-active")
    weekly = _last_success_for_job(db, "weekly-sold-rented")
    load_db = _last_success_for_job(db, "load-db")
    count: int | None = None
    try:
        count = db.scalar(select(func.count()).select_from(ActiveListing))
    except Exception:
        count = None
    parts: list[str] = []
    if daily and daily.finished_at:
        parts.append(
            "The daily listings refresh last finished OK at the times shown on this page (US Eastern)."
        )
    else:
        parts.append("No successful daily listings refresh has been recorded yet.")
    if count is not None:
        parts.append(f"About {count:,} active listings are stored in the database now.")
    else:
        parts.append("Active listing count could not be read from the database.")
    freshness = OpsActiveListingsFreshnessOut(
        message=" ".join(parts),
        active_listing_count=count,
    )
    ext = extended_host_metrics_if_enabled()
    return OpsOverviewOut(
        last_success_daily_active=daily,
        last_success_weekly=weekly,
        last_success_load_db=load_db,
        active_listings_freshness=freshness,
        extended_host_metrics=ext,
    )


@app.get("/ops/disk", response_model=OpsDiskOut, dependencies=[Depends(require_ops_auth)])
def ops_disk() -> OpsDiskOut:
    """Disk space for the filesystem that holds the project and heavy subfolders."""
    return OpsDiskOut(**disk_usage_snapshot(PROJECT_DIR))


@app.get("/ops/backup-status", response_model=OpsBackupStatusOut, dependencies=[Depends(require_ops_auth)])
def ops_backup_status() -> OpsBackupStatusOut:
    """Last Postgres backup heartbeat (written by backup_postgres.sh)."""
    return read_backup_status(PROJECT_DIR)


@app.get("/ops/schedule-status", response_model=list[OpsScheduleRowOut], dependencies=[Depends(require_ops_auth)])
def ops_schedule_status(db: Session = Depends(get_db)) -> list[OpsScheduleRowOut]:
    """Expected schedule hints vs latest run and latest success per job."""
    rows = build_schedule_rows(db)
    return [OpsScheduleRowOut(**r) for r in rows]


@app.get("/ops/runs", response_model=list[OpsRunRowOut], dependencies=[Depends(require_ops_auth)])
def list_pipeline_runs(
    limit: int = Query(default=50, ge=1, le=500),
    status: OpsRunStatusFilter = Query(default=OpsRunStatusFilter.all),
    sort: OpsRunSort = Query(default=OpsRunSort.recent),
    db: Session = Depends(get_db),
) -> list[OpsRunRowOut]:
    stmt = select(PipelineRun)
    if status == OpsRunStatusFilter.success:
        stmt = stmt.where(PipelineRun.exit_code == 0)
    elif status == OpsRunStatusFilter.failed:
        stmt = stmt.where(and_(PipelineRun.exit_code.isnot(None), PipelineRun.exit_code != 0))
    if sort == OpsRunSort.failures_first:
        fail_first = case(
            (and_(PipelineRun.exit_code.isnot(None), PipelineRun.exit_code != 0), 0),
            else_=1,
        )
        stmt = stmt.order_by(fail_first.asc(), desc(PipelineRun.started_at))
    else:
        stmt = stmt.order_by(desc(PipelineRun.started_at))
    stmt = stmt.limit(limit)
    rows = list(db.execute(stmt).scalars().all())
    return [OpsRunRowOut(**build_ops_run_row(r)) for r in rows]


@app.get(
    "/ops/runs/{run_id}/log-excerpt",
    response_model=OpsLogExcerptOut,
    dependencies=[Depends(require_ops_auth)],
)
def ops_run_log_excerpt(
    run_id: int,
    max_lines: int = Query(default=200, ge=10, le=500),
    db: Session = Depends(get_db),
) -> OpsLogExcerptOut:
    """Log lines for one run (anchored by PIPELINE_RUN_LOG_ANCHOR in rolling job logs)."""
    row = db.get(PipelineRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    path_str, content, note = read_run_log_excerpt(
        PROJECT_DIR, row.job_key, run_id, max_lines=max_lines
    )
    return OpsLogExcerptOut(
        run_id=run_id,
        job_key=row.job_key,
        resolved_path=path_str,
        content=content or "",
        note=note,
    )


@app.get("/ops/summary", response_model=list[OpsSummaryRow], dependencies=[Depends(require_ops_auth)])
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
        h = help_for(r.job_key)
        out.append(
            OpsSummaryRow(
                job_key=r.job_key,
                title=h.title,
                one_liner=h.one_liner,
                last_success_at=r.finished_at,
                last_exit_code=r.exit_code,
                run_id=r.id,
            )
        )
    return out


@app.get("/ops/log-tail", dependencies=[Depends(require_ops_auth)])
def ops_log_tail(
    job_key: str = Query(..., description="Pipeline job key, e.g. daily-active"),
    lines: int = Query(default=300, ge=50, le=500),
) -> dict[str, str | None]:
    """Tail end of the rolling log file for a job (same files cron appends to)."""
    path_str, content, err = read_log_tail(PROJECT_DIR, job_key, max_lines=lines)
    return {
        "job_key": job_key,
        "resolved_path": path_str,
        "content": content or "",
        "error": err,
    }


@app.get("/ops/runs/{run_id}", response_model=OpsRunRowOut, dependencies=[Depends(require_ops_auth)])
def get_pipeline_run(run_id: int, db: Session = Depends(get_db)) -> OpsRunRowOut:
    row = db.get(PipelineRun, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return OpsRunRowOut(**build_ops_run_row(row))


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

    Uses the DB snapshot refreshed by ``load_to_db`` from ``sold_clean_latest.csv``, filtered by ZIP /
    town / bedrooms / property type, and looks back roughly ``months_back`` months based on settled date.
    """

    try:
        df = _load_sold_df(db)
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
        df = _load_sold_df(db)
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


@app.get("/finance/mortgage-presets")
def mortgage_presets() -> dict:
    """Illustrative mortgage product presets (same contract as dashboard defaults)."""
    return mortgage_presets_payload()


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
