from pathlib import Path

import pandas as pd
import pytest

import data_quality


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


@pytest.fixture
def quality_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    combined = tmp_path / "combined"
    cleaned = tmp_path / "cleaned"
    analytics = tmp_path / "analytics"
    combined.mkdir()
    cleaned.mkdir()
    analytics.mkdir()
    monkeypatch.setattr(data_quality, "COMBINED_DIR", combined)
    monkeypatch.setattr(data_quality, "CLEANED_DIR", cleaned)
    monkeypatch.setattr(data_quality, "ANALYTICS_DIR", analytics)
    return tmp_path


def test_validate_monthly_outputs_passes_with_expected_files(quality_dirs: Path) -> None:
    _write_csv(
        quality_dirs / "combined" / "sold_master_latest.csv",
        [{"mls_id": "1", "sale_price": 500000}],
    )
    _write_csv(
        quality_dirs / "combined" / "rentals_master_latest.csv",
        [{"mls_id": "2", "rent_price": 2600}],
    )
    _write_csv(
        quality_dirs / "cleaned" / "sold_clean_latest.csv",
        [{"zip_code": "02134", "sale_price": 500000, "bedrooms": 3, "settled_date": "2026-05-01"}],
    )
    _write_csv(
        quality_dirs / "cleaned" / "rentals_clean_latest.csv",
        [{"zip_code": "02139", "rent_price": 3200}],
    )
    _write_csv(
        quality_dirs / "analytics" / "rent_by_zip_bedrooms.csv",
        [{"zip_code": f"021{i:02d}", "bedrooms": 2, "avg_rent": 3000} for i in range(120)],
    )
    _write_csv(
        quality_dirs / "analytics" / "rent_by_zip_sqft.csv",
        [{"zip_code": "02139", "avg_rent_per_sqft": 3.2}],
    )

    data_quality.validate_monthly_outputs()


def test_validate_monthly_outputs_rejects_short_numeric_zip(quality_dirs: Path) -> None:
    _write_csv(quality_dirs / "combined" / "sold_master_latest.csv", [{"mls_id": "1"}])
    _write_csv(quality_dirs / "combined" / "rentals_master_latest.csv", [{"mls_id": "2"}])
    _write_csv(
        quality_dirs / "cleaned" / "sold_clean_latest.csv",
        [{"zip_code": "02134", "sale_price": 500000, "bedrooms": 2, "settled_date": "2026-05-01"}],
    )
    _write_csv(
        quality_dirs / "cleaned" / "rentals_clean_latest.csv",
        [{"zip_code": "2134", "rent_price": 2800}],
    )
    _write_csv(
        quality_dirs / "analytics" / "rent_by_zip_bedrooms.csv",
        [{"zip_code": f"021{i:02d}", "bedrooms": 1, "avg_rent": 2000} for i in range(120)],
    )
    _write_csv(
        quality_dirs / "analytics" / "rent_by_zip_sqft.csv",
        [{"zip_code": "02139", "avg_rent_per_sqft": 3.0}],
    )

    with pytest.raises(ValueError, match="short numeric ZIP"):
        data_quality.validate_monthly_outputs()


def test_validate_daily_active_outputs_rejects_empty_csv(quality_dirs: Path) -> None:
    active_path = quality_dirs / "cleaned" / "active_clean_latest.csv"
    active_path.write_text("mls_id,status\n", encoding="utf-8")

    with pytest.raises(ValueError, match="active_clean_latest.csv is empty"):
        data_quality.validate_daily_active_outputs()


def test_validate_daily_active_outputs_passes_with_rows(quality_dirs: Path) -> None:
    _write_csv(
        quality_dirs / "cleaned" / "active_clean_latest.csv",
        [{"mls_id": "A1", "status": "ACTIVE"}],
    )

    data_quality.validate_daily_active_outputs()
