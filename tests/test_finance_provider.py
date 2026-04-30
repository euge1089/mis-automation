from backend.enrichment.contracts import FinanceRateProvider
from backend.finance_provider import StaticFinanceRateProvider, mortgage_presets_payload


def test_static_provider_matches_protocol() -> None:
    p = StaticFinanceRateProvider()
    assert isinstance(p, FinanceRateProvider)
    assert "30fixed" in p.presets()


def test_payload_includes_schema_version() -> None:
    body = mortgage_presets_payload()
    assert body["schema_version"] == 1
    assert len(body["presets"]) >= 4
