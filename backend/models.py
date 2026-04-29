from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class ActiveListing(Base):
    __tablename__ = "active_listings"

    mls_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str | None] = mapped_column(String(64))
    property_type: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(Text)
    town: Mapped[str | None] = mapped_column(String(128), index=True)
    state: Mapped[str | None] = mapped_column(String(16))
    zip_code: Mapped[str | None] = mapped_column(String(10), index=True)
    bedrooms: Mapped[float | None] = mapped_column(Float)
    total_baths: Mapped[float | None] = mapped_column(Float)
    square_feet: Mapped[float | None] = mapped_column(Float)
    list_price: Mapped[float | None] = mapped_column(Float, index=True)
    taxes: Mapped[float | None] = mapped_column(Float)
    tax_year: Mapped[float | None] = mapped_column(Float)
    lot_size: Mapped[float | None] = mapped_column(Float)
    year_built: Mapped[float | None] = mapped_column(Float)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    county: Mapped[str | None] = mapped_column(String(128))
    neighborhood: Mapped[str | None] = mapped_column(String(128))
    full_address: Mapped[str | None] = mapped_column(Text)


class RentByZipBedroom(Base):
    __tablename__ = "rent_by_zip_bedroom"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zip_code: Mapped[str] = mapped_column(String(10), index=True)
    bedrooms: Mapped[float] = mapped_column(Float, index=True)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    avg_rent: Mapped[float | None] = mapped_column(Float)
    median_rent: Mapped[float | None] = mapped_column(Float)
    min_rent: Mapped[float | None] = mapped_column(Float)
    max_rent: Mapped[float | None] = mapped_column(Float)
    avg_sqft: Mapped[float | None] = mapped_column(Float)
    median_sqft: Mapped[float | None] = mapped_column(Float)
    avg_rent_per_sqft: Mapped[float | None] = mapped_column(Float)
    median_rent_per_sqft: Mapped[float | None] = mapped_column(Float)
    towns_seen: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(32))


class RentByZipSqft(Base):
    __tablename__ = "rent_by_zip_sqft"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    zip_code: Mapped[str] = mapped_column(String(10), index=True)
    sample_size: Mapped[int | None] = mapped_column(Integer)
    avg_rent: Mapped[float | None] = mapped_column(Float)
    median_rent: Mapped[float | None] = mapped_column(Float)
    avg_sqft: Mapped[float | None] = mapped_column(Float)
    median_sqft: Mapped[float | None] = mapped_column(Float)
    avg_rent_per_sqft: Mapped[float | None] = mapped_column(Float)
    median_rent_per_sqft: Mapped[float | None] = mapped_column(Float)
    towns_seen: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(32))


class SoldListingHistory(Base):
    __tablename__ = "sold_listing_history"
    __table_args__ = (
        UniqueConstraint("mls_id", "event_date", "status", name="uq_sold_history_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mls_id: Mapped[str] = mapped_column(String(64), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str | None] = mapped_column(String(64))
    property_type: Mapped[str | None] = mapped_column(String(64))
    town: Mapped[str | None] = mapped_column(String(128), index=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), index=True)
    sale_price: Mapped[float | None] = mapped_column(Float)
    bedrooms: Mapped[float | None] = mapped_column(Float)
    total_baths: Mapped[float | None] = mapped_column(Float)
    square_feet: Mapped[float | None] = mapped_column(Float)
    source_window_start: Mapped[date | None] = mapped_column(Date)
    source_window_end: Mapped[date | None] = mapped_column(Date)
    memorialized_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class RentedListingHistory(Base):
    __tablename__ = "rented_listing_history"
    __table_args__ = (
        UniqueConstraint("mls_id", "event_date", "status", name="uq_rented_history_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mls_id: Mapped[str] = mapped_column(String(64), index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str | None] = mapped_column(String(64))
    property_type: Mapped[str | None] = mapped_column(String(64))
    town: Mapped[str | None] = mapped_column(String(128), index=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), index=True)
    rent_price: Mapped[float | None] = mapped_column(Float)
    bedrooms: Mapped[float | None] = mapped_column(Float)
    total_baths: Mapped[float | None] = mapped_column(Float)
    square_feet: Mapped[float | None] = mapped_column(Float)
    source_window_start: Mapped[date | None] = mapped_column(Date)
    source_window_end: Mapped[date | None] = mapped_column(Date)
    memorialized_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    payload_json: Mapped[str] = mapped_column(Text)


class PipelineRun(Base):
    """One row per ``pipeline.py`` invocation (scheduled or manual)."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_key: Mapped[str] = mapped_column(String(64), index=True)
    argv_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    hostname: Mapped[str | None] = mapped_column(String(256), nullable=True)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
