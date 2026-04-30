"""Typed contracts for enrichment modules (Phase 6). Implementations are swapped without scraper changes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class EnrichmentMeta:
    """How/when an enrichment was produced (for API explainability)."""

    source: str
    as_of: date
    confidence: str | None = None
    caveats: str | None = None


@runtime_checkable
class SchoolEnrichmentSource(Protocol):
    """Nearest school / district context keyed by lat/lon or address."""

    def lookup(self, *, lat: float | None, lon: float | None, zip_code: str | None) -> dict[str, Any]:
        ...


@runtime_checkable
class HealthcareEnrichmentSource(Protocol):
    """Proximity to hospitals/clinics."""

    def lookup(self, *, lat: float | None, lon: float | None, zip_code: str | None) -> dict[str, Any]:
        ...


@runtime_checkable
class FinanceRateProvider(Protocol):
    """Mortgage / finance assumptions for carry estimates (static now, partner API later)."""

    def presets(self) -> dict[str, Any]:
        ...
