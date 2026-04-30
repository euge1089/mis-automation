#!/usr/bin/env python3
"""Compare two MLS-style active listing CSVs by normalized ZIP (Phase 7 harness).

Example:
  python scripts/compare_listing_sources.py path/to/a.csv path/to/b.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare active listing exports by ZIP.")
    ap.add_argument("left", type=Path, help="CSV path (e.g. scraper export)")
    ap.add_argument("right", type=Path, help="CSV path (e.g. VOW staging)")
    ap.add_argument("--zip-col", default="zip_code", help="ZIP column name (default zip_code)")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    import pandas as pd

    from backend.zip_normalize import normalize_us_zip_5

    for label, path in ("left", args.left), ("right", args.right):
        if not path.exists():
            print(json.dumps({"error": f"{label} not found", "path": str(path)}))
            return 2

    left = pd.read_csv(args.left, low_memory=False)
    right = pd.read_csv(args.right, low_memory=False)
    zc = args.zip_col
    if zc not in left.columns or zc not in right.columns:
        print(json.dumps({"error": f"missing column {zc!r}", "left_cols": list(left.columns)[:20]}))
        return 2

    def counts(df: pd.DataFrame) -> dict[str, int]:
        out: dict[str, int] = {}
        for raw in df[zc].astype("string"):
            z = normalize_us_zip_5(str(raw)) or ""
            out[z] = out.get(z, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    lc, rc = counts(left), counts(right)
    keys = sorted(set(lc) | set(rc))
    deltas = []
    for k in keys:
        a, b = lc.get(k, 0), rc.get(k, 0)
        if a != b:
            deltas.append({"zip": k or "(blank)", "left": a, "right": b, "delta": b - a})

    report = {
        "left_rows": len(left),
        "right_rows": len(right),
        "zip_buckets_left": len(lc),
        "zip_buckets_right": len(rc),
        "mismatched_zip_buckets": len(deltas),
        "sample_deltas": deltas[:50],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
