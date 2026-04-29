#!/usr/bin/env python3
"""
Compare rental CSV downloads → combined → cleaned → analytics → Postgres.

The dashboard rent table uses **aggregated** rent-by-ZIP-bedroom rows in the database
(not every individual lease). If counts look low, re-run the monthly pipeline and load-db.

Usage (from project root):
  python3 check_rental_data.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import func, select

from backend.db import SessionLocal
from backend.models import RentByZipBedroom

PROJECT = Path(__file__).resolve().parent
DL = PROJECT / "downloads" / "rentals"
COMBINED = PROJECT / "combined" / "rentals_master_latest.csv"
CLEANED = PROJECT / "cleaned" / "rentals_clean_latest.csv"
ANALYTICS = PROJECT / "analytics" / "rent_by_zip_bedrooms.csv"


def _mtime(p: Path) -> str:
    if not p.exists():
        return "(missing)"
    from datetime import datetime

    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def main() -> None:
    print("=== Rental data sync check ===\n")

    files = sorted(DL.glob("rentals_export_*.csv"))
    print(f"downloads/rentals: {len(files)} CSV file(s)")
    if files:
        print(f"  Newest download: {_mtime(files[-1])}  ({files[-1].name})")
    print()

    for label, path in [
        ("combined/rentals_master_latest.csv", COMBINED),
        ("cleaned/rentals_clean_latest.csv", CLEANED),
        ("analytics/rent_by_zip_bedrooms.csv", ANALYTICS),
    ]:
        if not path.exists():
            print(f"{label}: MISSING — run: python3 pipeline.py monthly")
            continue
        df = pd.read_csv(path, low_memory=False)
        print(f"{label}: {len(df):,} rows  ·  last modified {_mtime(path)}")

    print()
    try:
        with SessionLocal() as session:
            n = session.execute(select(func.count()).select_from(RentByZipBedroom)).scalar_one()
        print(f"Database rent_by_zip_bedroom: {n:,} rows")
        if ANALYTICS.exists():
            df_a = pd.read_csv(ANALYTICS, low_memory=False)
            if len(df_a) != n:
                print(
                    f"  ⚠ Row count differs from analytics file ({len(df_a):,}). "
                    "Run: python3 pipeline.py load-db"
                )
    except Exception as exc:
        print(f"Database: could not query ({exc}). Is Docker up? docker compose up -d db")

    print()
    print("If downloads are newer than combined/cleaned, refresh everything:")
    print("  python3 pipeline.py monthly")
    print("  python3 pipeline.py validate-monthly")
    print("  python3 pipeline.py load-db")
    print()
    print("Note: The website shows rent **summaries by ZIP + bedrooms**, not every rental row.")


if __name__ == "__main__":
    main()
