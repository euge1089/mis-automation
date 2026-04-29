"""Raw MLS export paths and cleanup between scrape windows.

Sold exports live at ``downloads/mls_export_*.csv``; rentals at
``downloads/rentals/rentals_export_*.csv``. Active exports under
``downloads/active/`` are never touched here.

Clearing before each scraped window keeps ``combine_*`` from merging slices
from older memorialized windows (Postgres already holds closed months).
"""

from __future__ import annotations

from pathlib import Path


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
