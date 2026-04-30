from pathlib import Path

from storage_paths import clear_active_raw_downloads, clear_sold_and_rental_raw_downloads


def test_clear_sold_and_rental_raw_downloads_removes_only_those(tmp_path: Path) -> None:
    root = tmp_path
    (root / "downloads").mkdir()
    (root / "downloads" / "active").mkdir()
    (root / "downloads" / "mls_export_1.csv").write_text("a")
    (root / "downloads" / "rentals").mkdir()
    (root / "downloads" / "rentals" / "rentals_export_1.csv").write_text("b")
    (root / "downloads" / "active" / "active_export_1.csv").write_text("keep")

    counts = clear_sold_and_rental_raw_downloads(root)
    assert counts == {"sold": 1, "rentals": 1}
    assert not (root / "downloads" / "mls_export_1.csv").exists()
    assert not (root / "downloads" / "rentals" / "rentals_export_1.csv").exists()
    assert (root / "downloads" / "active" / "active_export_1.csv").read_text() == "keep"


def test_clear_active_raw_downloads_removes_only_active_slices(tmp_path: Path) -> None:
    root = tmp_path
    (root / "downloads" / "active").mkdir(parents=True)
    (root / "downloads" / "active" / "active_export_0_100.csv").write_text("h\n1\n")
    (root / "downloads" / "active" / "other.csv").write_text("x")
    (root / "downloads" / "mls_export_1.csv").write_text("sold")

    n = clear_active_raw_downloads(root)
    assert n == 1
    assert not (root / "downloads" / "active" / "active_export_0_100.csv").exists()
    assert (root / "downloads" / "active" / "other.csv").read_text() == "x"
    assert (root / "downloads" / "mls_export_1.csv").read_text() == "sold"
