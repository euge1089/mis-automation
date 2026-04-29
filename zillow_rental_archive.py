"""
Rolling archive for Zillow rental snapshots.

Each scrape run merges new listing rows keyed by ``zpid``. Rows that disappear from Zillow
stop getting ``last_seen_utc`` updates; ``prune_stale`` drops them after they have not been
seen for ``stale_days`` (default 365), which yields a rolling ~year of "recently observed"
rental inventory without unbounded growth.

This does not replace MLS rented history; it builds a separate longitudinal view from
whatever Zillow exposes on public search (mostly *for rent* inventory).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ARCHIVE_COLUMNS = [
    "zpid",
    "detail_url",
    "address",
    "city_state",
    "zip_code",
    "rent",
    "beds",
    "baths",
    "sqft",
    "first_seen_utc",
    "last_seen_utc",
    "observation_count",
]


def default_archive_path(project_root: Path) -> Path:
    return project_root / "data" / "zillow" / "rentals_archive.csv"


def load_archive(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=ARCHIVE_COLUMNS)
    df = pd.read_csv(path, dtype={"zpid": str}, low_memory=False)
    for col in ARCHIVE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["zpid"] = df["zpid"].astype(str)
    if "observation_count" in df.columns:
        df["observation_count"] = df["observation_count"].fillna(1).astype(int)
    df = df.drop_duplicates(subset=["zpid"], keep="last")
    return df[ARCHIVE_COLUMNS]


def merge_snapshot(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    now: datetime | None = None,
) -> pd.DataFrame:
    """
    Upsert by zpid. Existing first_seen_utc preserved; last_seen_utc and numeric fields
    refresh from the latest scrape; observation_count increments when zpid seen again.
    """
    now = now or datetime.now(timezone.utc)
    ts = now.isoformat()

    if incoming is None or incoming.empty:
        return existing.copy() if not existing.empty else pd.DataFrame(columns=ARCHIVE_COLUMNS)

    inc = incoming.copy()
    inc["zpid"] = inc["zpid"].astype(str)
    inc = inc.drop_duplicates(subset=["zpid"], keep="last")

    if existing is None or existing.empty:
        out = inc.copy()
        out["first_seen_utc"] = ts
        out["last_seen_utc"] = ts
        out["observation_count"] = 1
        return out[ARCHIVE_COLUMNS]

    old = existing.copy()
    old["zpid"] = old["zpid"].astype(str)
    old_by_z = old.set_index("zpid", drop=False)

    new_zpids = set(inc["zpid"])
    unchanged = old[~old["zpid"].isin(new_zpids)]

    update_rows = []
    for _, row in inc.iterrows():
        z = row["zpid"]
        base = {
            "zpid": z,
            "detail_url": row.get("detail_url", ""),
            "address": row.get("address", ""),
            "city_state": row.get("city_state", ""),
            "zip_code": row.get("zip_code", ""),
            "rent": row.get("rent"),
            "beds": row.get("beds"),
            "baths": row.get("baths"),
            "sqft": row.get("sqft"),
            "last_seen_utc": ts,
        }
        if z in old_by_z.index:
            prev = old_by_z.loc[z]
            if isinstance(prev, pd.DataFrame):
                prev = prev.iloc[0]
            base["first_seen_utc"] = prev["first_seen_utc"]
            base["observation_count"] = int(prev.get("observation_count", 1) or 1) + 1
        else:
            base["first_seen_utc"] = ts
            base["observation_count"] = 1
        update_rows.append(base)

    updated = pd.DataFrame(update_rows)
    out = pd.concat([unchanged, updated], ignore_index=True)
    out = out.drop_duplicates(subset=["zpid"], keep="last")
    return out[ARCHIVE_COLUMNS]


def prune_stale(
    df: pd.DataFrame,
    *,
    stale_days: int,
    now: datetime | None = None,
) -> tuple[pd.DataFrame, int]:
    """Drop rows whose last_seen_utc is older than ``now - stale_days``."""
    now = now or datetime.now(timezone.utc)
    if df is None or df.empty:
        return df, 0
    cutoff = now - timedelta(days=stale_days)
    last = pd.to_datetime(df["last_seen_utc"], utc=True, errors="coerce")
    keep = last >= pd.Timestamp(cutoff).tz_convert("UTC")
    removed = int((~keep).sum())
    return df.loc[keep].copy(), removed


def save_archive(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
