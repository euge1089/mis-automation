"""Contract sanity checks for enrichment Protocols (Phase 6)."""

from backend.enrichment.contracts import HealthcareEnrichmentSource, SchoolEnrichmentSource


def test_protocols_are_runtime_checkable() -> None:
    class DummySchools:
        def lookup(self, *, lat=None, lon=None, zip_code=None):
            return {"district": "dummy"}

    assert isinstance(DummySchools(), SchoolEnrichmentSource)

    class DummyHealth:
        def lookup(self, *, lat=None, lon=None, zip_code=None):
            return {"nearest_hospital_mi": 1.2}

    assert isinstance(DummyHealth(), HealthcareEnrichmentSource)
