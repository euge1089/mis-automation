from __future__ import annotations

from datetime import date, datetime

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
