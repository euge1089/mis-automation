from __future__ import annotations

from datetime import date

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
