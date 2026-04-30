"""Schedule vs last-run rows for the ops dashboard."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.models import PipelineRun
from backend.ops_catalog import JOB_HELP


def build_schedule_rows(db: Session) -> list[dict[str, object]]:
    """One row per known job: catalog copy plus latest any run and latest success."""
    rows = list(db.execute(select(PipelineRun).order_by(desc(PipelineRun.started_at))).scalars().all())
    latest_run: dict[str, PipelineRun] = {}
    latest_success: dict[str, PipelineRun] = {}
    for r in rows:
        if r.job_key not in latest_run:
            latest_run[r.job_key] = r
        if r.exit_code == 0 and r.finished_at is not None and r.job_key not in latest_success:
            latest_success[r.job_key] = r

    out: list[dict[str, object]] = []
    for key in sorted(JOB_HELP.keys(), key=lambda k: JOB_HELP[k].title.lower()):
        h = JOB_HELP[key]
        lr = latest_run.get(key)
        ls = latest_success.get(key)
        out.append(
            {
                "job_key": key,
                "title": h.title,
                "schedule_hint": h.schedule_hint,
                "last_run_started_at": lr.started_at if lr else None,
                "last_run_finished_at": lr.finished_at if lr else None,
                "last_run_exit_code": lr.exit_code if lr else None,
                "last_success_at": ls.finished_at if ls else None,
            }
        )
    return out
