from pathlib import Path

from backend.listing_sources.active_listings import ScraperActiveListingSource


def test_scraper_adapter_has_stable_name() -> None:
    src = ScraperActiveListingSource()
    assert src.name == "mls_pinergy_scraper"
    assert hasattr(src, "run_export")


def test_project_stub_paths_exist() -> None:
    """Smoke check repo layout expected by adapters."""
    root = Path(__file__).resolve().parents[1]
    assert (root / "scrape_mls_active.py").is_file()
