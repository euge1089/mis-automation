"""
Resume long MLS export runs from existing per-band CSV filenames.

Each successful download saves ``{prefix}{start}_{end}.csv``. On the next run we take the
largest ``end`` seen and continue from ``end + 1`` so a daily download limit does not
lose progress.
"""
from __future__ import annotations

import re
from pathlib import Path

# Shown when Playwright times out waiting for a file download to begin.
MLS_DOWNLOAD_TIMEOUT_HINT = """
======================================================================
Download did not start (timeout). Common causes:
  - MLS daily export cap (~100/day). Continue tomorrow: rentals/active resume from saved CSVs;
    sold homes:  python3 scrape_mls_sold.py --resume
  - Running sold (scrape_mls_sold.py) and rentals (scrape_mls_rented.py) the same day can hit the cap;
    stagger them across days when possible.
  - Rentals/active: use --from-start to ignore saved CSVs. Sold: each run is fresh by default;
    use --resume only to continue a partial sold run.
======================================================================
""".strip()


def max_export_end_in_dir(downloads_dir: Path, prefix: str) -> int | None:
    """
    Return the largest ``end`` in files named ``{prefix}{start}_{end}.csv``.
    """
    if not downloads_dir.is_dir():
        return None
    rx = re.compile(rf"^{re.escape(prefix)}(\d+)_(\d+)\.csv$", re.IGNORECASE)
    best: int | None = None
    for path in downloads_dir.iterdir():
        if not path.is_file() or path.suffix.lower() != ".csv":
            continue
        m = rx.match(path.name)
        if not m:
            continue
        end = int(m.group(2))
        if best is None or end > best:
            best = end
    return best


def resolved_start_export_resume(
    downloads_dir: Path,
    prefix: str,
    default_start: int,
    max_bound: int,
    *,
    from_start: bool,
) -> tuple[int, int | None]:
    """
    Returns (next_start, last_completed_end or None).

    If ``from_start``, next_start is ``default_start`` and last end is None for messaging.
    """
    if from_start:
        return default_start, None
    last_end = max_export_end_in_dir(downloads_dir, prefix)
    if last_end is None:
        return default_start, None
    return last_end + 1, last_end
