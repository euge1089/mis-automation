from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ActiveListingOut(BaseModel):
    mls_id: str
    status: str | None
    property_type: str | None
    address: str | None
    town: str | None
    state: str | None
    zip_code: str | None
    bedrooms: float | None
    total_baths: float | None
    square_feet: float | None
    list_price: float | None
    taxes: float | None
    tax_year: float | None
    lot_size: float | None
    year_built: float | None
    latitude: float | None
    longitude: float | None
    county: str | None
    neighborhood: str | None
    full_address: str | None

    class Config:
        from_attributes = True


class GeocodeBatchIn(BaseModel):
    """Small batches to respect Nominatim ~1 req/s and avoid HTTP timeouts."""

    mls_ids: list[str] = Field(..., min_length=1, max_length=8)


class GeocodeUpdateOut(BaseModel):
    mls_id: str
    latitude: float
    longitude: float


class RentByZipBedroomOut(BaseModel):
    zip_code: str
    bedrooms: float
    sample_size: int | None
    avg_rent: float | None
    median_rent: float | None
    min_rent: float | None
    max_rent: float | None
    avg_sqft: float | None
    median_sqft: float | None
    avg_rent_per_sqft: float | None
    median_rent_per_sqft: float | None
    towns_seen: str | None
    confidence: str | None

    class Config:
        from_attributes = True


class RentByZipSqftOut(BaseModel):
    zip_code: str
    sample_size: int | None
    avg_rent: float | None
    median_rent: float | None
    avg_sqft: float | None
    median_sqft: float | None
    avg_rent_per_sqft: float | None
    median_rent_per_sqft: float | None
    towns_seen: str | None
    confidence: str | None

    class Config:
        from_attributes = True


class SoldListingHistoryOut(BaseModel):
    mls_id: str
    event_date: date
    status: str | None
    property_type: str | None
    town: str | None
    zip_code: str | None
    sale_price: float | None
    bedrooms: float | None
    total_baths: float | None
    square_feet: float | None

    class Config:
        from_attributes = True


class PipelineRunOut(BaseModel):
    id: int
    job_key: str
    argv_json: dict | list | None = None
    started_at: datetime
    finished_at: datetime | None = None
    exit_code: int | None = None
    hostname: str | None = None
    git_sha: str | None = None
    detail_json: dict | None = None

    class Config:
        from_attributes = True


class JobCatalogItemOut(BaseModel):
    job_key: str
    title: str
    one_liner: str
    what_it_does: str
    success_means: str
    schedule_hint: str


class OpsRunStatusFilter(str, Enum):
    all = "all"
    success = "success"
    failed = "failed"


class OpsRunSort(str, Enum):
    recent = "recent"
    failures_first = "failures_first"


class OpsRunRowOut(BaseModel):
    """Pipeline run plus plain-language fields for the ops UI."""

    id: int
    job_key: str
    title: str
    one_liner: str
    what_it_does: str
    schedule_hint: str
    started_at: datetime
    finished_at: datetime | None = None
    exit_code: int | None = None
    hostname: str | None = None
    git_sha: str | None = None
    headline_status: str
    success_message: str
    metric_lines: list[str]
    detail_json: dict | None = None
    argv_json: dict | list | None = None
    error_summary: str | None = None


class DailyActiveDropStatusOut(BaseModel):
    status: str
    message: str
    latest_count: int | None = None
    previous_count: int | None = None
    pct_change_vs_prior: float | None = None
    threshold_pct: float


class OpsAlertsBundleOut(BaseModel):
    slack_configured: bool
    active_drop_threshold_pct: float
    sold_rent_min_rows: int
    alert_blurbs: dict[str, str]
    daily_active_drop: DailyActiveDropStatusOut


class OpsSummaryRow(BaseModel):
    job_key: str
    title: str | None = None
    one_liner: str | None = None
    last_success_at: datetime | None = None
    last_exit_code: int | None = None
    run_id: int | None = None


class OpsLastSuccessOut(BaseModel):
    finished_at: datetime | None = None
    run_id: int | None = None


class OpsActiveListingsFreshnessOut(BaseModel):
    """Plain-language freshness; listing count when the DB is reachable."""

    source: str = Field(default="proxy_and_count")
    message: str
    active_listing_count: int | None = None


class OpsOverviewOut(BaseModel):
    api_ok: bool = True
    last_success_daily_active: OpsLastSuccessOut | None = None
    last_success_weekly: OpsLastSuccessOut | None = None
    last_success_load_db: OpsLastSuccessOut | None = None
    active_listings_freshness: OpsActiveListingsFreshnessOut
    extended_host_metrics: dict[str, str] | None = None


class OpsDiskOut(BaseModel):
    project_path: str
    filesystem_total_bytes: int
    filesystem_used_bytes: int
    filesystem_free_bytes: int
    filesystem_used_pct: float
    heavy_dirs_bytes: dict[str, int | None]


class OpsBackupStatusOut(BaseModel):
    status: str
    message: str
    heartbeat_path: str | None = None
    last_backup_utc: str | None = None


class OpsLogExcerptOut(BaseModel):
    run_id: int
    job_key: str
    resolved_path: str | None = None
    content: str
    note: str | None = None


class OpsScheduleRowOut(BaseModel):
    job_key: str
    title: str
    schedule_hint: str
    last_run_started_at: datetime | None = None
    last_run_finished_at: datetime | None = None
    last_run_exit_code: int | None = None
    last_success_at: datetime | None = None


class RentedListingHistoryOut(BaseModel):
    mls_id: str
    event_date: date
    status: str | None
    property_type: str | None
    town: str | None
    zip_code: str | None
    rent_price: float | None
    bedrooms: float | None
    total_baths: float | None
    square_feet: float | None

    class Config:
        from_attributes = True
