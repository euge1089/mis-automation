"""Alert settings and status for the ops dashboard (no secrets exposed)."""

from __future__ import annotations

import os

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.models import PipelineRun
from backend.ops_catalog import ALERT_COPY


def alert_settings() -> dict[str, object]:
    slack = bool(os.environ.get("SLACK_WEBHOOK_URL", "").strip())
    try:
        pct = float(os.environ.get("ACTIVE_DROP_ALERT_PCT", "35"))
    except ValueError:
        pct = 35.0
    try:
        min_rows = int(os.environ.get("SOLD_RENTED_MIN_ROWS", "100"))
    except ValueError:
        min_rows = 100
    return {
        "slack_configured": slack,
        "active_drop_threshold_pct": pct,
        "sold_rent_min_rows": min_rows,
        "alert_blurbs": ALERT_COPY,
    }


def _int_from_detail(detail: object | None, key: str) -> int | None:
    if not isinstance(detail, dict):
        return None
    v = detail.get(key)
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return None


def daily_active_drop_status(db: Session, threshold_pct: float) -> dict[str, object]:
    """Compare last two successful daily-active runs by cleaned active count."""
    rows = list(
        db.execute(
            select(PipelineRun)
            .where(PipelineRun.job_key == "daily-active")
            .where(PipelineRun.exit_code == 0)
            .where(PipelineRun.finished_at.isnot(None))
            .order_by(desc(PipelineRun.finished_at))
            .limit(2)
        )
        .scalars()
        .all()
    )
    if len(rows) < 2:
        return {
            "status": "insufficient_data",
            "message": "Need at least two successful daily-active runs with saved metrics to compare.",
            "latest_count": None,
            "previous_count": None,
            "pct_change_vs_prior": None,
            "threshold_pct": threshold_pct,
        }
    latest, previous = rows[0], rows[1]
    cur = _int_from_detail(latest.detail_json, "active_listings_after_cleaning")
    prev = _int_from_detail(previous.detail_json, "active_listings_after_cleaning")
    if cur is None or prev is None:
        return {
            "status": "insufficient_data",
            "message": "Recent runs are missing listing counts — metrics will appear after the next successful run.",
            "latest_count": cur,
            "previous_count": prev,
            "pct_change_vs_prior": None,
            "threshold_pct": threshold_pct,
        }
    if prev <= 0:
        return {
            "status": "insufficient_data",
            "message": "Previous run had no baseline count to compare against.",
            "latest_count": cur,
            "previous_count": prev,
            "pct_change_vs_prior": None,
            "threshold_pct": threshold_pct,
        }
    # Negative => fewer listings than last successful run.
    pct_change = (cur - prev) / prev * 100.0
    decline_pct = -pct_change if pct_change < 0 else 0.0
    if pct_change < 0 and decline_pct >= threshold_pct:
        return {
            "status": "warn",
            "message": (
                f"Active listings fell about {decline_pct:.1f}% ({prev:,} → {cur:,}). "
                f"The alert threshold is a {threshold_pct:g}% drop — this often means a scrape or export issue."
            ),
            "latest_count": cur,
            "previous_count": prev,
            "pct_change_vs_prior": round(pct_change, 2),
            "threshold_pct": threshold_pct,
        }
    if pct_change >= 0:
        msg = (
            f"Listing count stayed flat or grew compared with the prior successful run ({prev:,} → {cur:,}). "
            f"We only warn on large drops (about {threshold_pct:g}% or more)."
        )
    else:
        msg = (
            f"Listing count dipped about {decline_pct:.1f}% ({prev:,} → {cur:,}), "
            f"which is below the {threshold_pct:g}% alert threshold."
        )
    return {
        "status": "ok",
        "message": msg,
        "latest_count": cur,
        "previous_count": prev,
        "pct_change_vs_prior": round(pct_change, 2),
        "threshold_pct": threshold_pct,
    }
