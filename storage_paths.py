"""Raw MLS export paths and cleanup between scrape windows.

Sold exports live at ``downloads/mls_export_*.csv``; rentals at
``downloads/rentals/rentals_export_*.csv``. Active exports live under
``downloads/active/active_export_*.csv``.

``clear_sold_and_rental_raw_downloads`` runs before sold/rent scrapes so combines
do not mix windows. ``clear_active_raw_downloads`` runs before the **daily active**
scrape so each run pulls fresh MLS slices instead of resuming stale files from
prior days (Postgres active listings are still fully replaced on each ``load-db``
via ``delete(ActiveListing)`` + insert).
"""

from __future__ import annotations

from pathlib import Path


def clear_active_raw_downloads(project_dir: Path) -> int:
    """
    Delete ``downloads/active/active_export_*.csv`` slice files.

    Used before ``daily-active`` scraping so prior-day exports are not reused.
    Returns the number of files removed.
    """
    active_dir = project_dir / "downloads" / "active"
    if not active_dir.is_dir():
        return 0
    n = 0
    for path in sorted(active_dir.glob("active_export_*.csv")):
        path.unlink()
        n += 1
    return n


def clear_sold_and_rental_raw_downloads(project_dir: Path) -> dict[str, int]:
    """
    Delete raw sold/rental CSVs only (not active).

    Returns counts of removed files: ``sold``, ``rentals``.
    """
    removed = {"sold": 0, "rentals": 0}
    for path in sorted(project_dir.glob("downloads/mls_export_*.csv")):
        path.unlink()
        removed["sold"] += 1
    rentals_dir = project_dir / "downloads" / "rentals"
    if rentals_dir.is_dir():
        for path in sorted(rentals_dir.glob("rentals_export_*.csv")):
            path.unlink()
            removed["rentals"] += 1
    return removed
