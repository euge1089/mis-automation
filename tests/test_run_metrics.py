"""Tests for pipeline post-run file/row metrics."""

from pathlib import Path

from backend.run_metrics import _sum_csv_data_rows_glob


def test_sum_csv_data_rows_glob_totals_data_rows(tmp_path: Path) -> None:
    d = tmp_path / "active"
    d.mkdir()
    (d / "a.csv").write_text("header\n1\n2\n", encoding="utf-8")
    (d / "b.csv").write_text("header\n3\n", encoding="utf-8")
    assert _sum_csv_data_rows_glob(d, "*.csv") == 3


def test_sum_csv_data_rows_glob_empty_dir(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    assert _sum_csv_data_rows_glob(d, "*.csv") == 0
