"""Persist pipeline.py execution records for the ops dashboard."""

from __future__ import annotations

import logging
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.db import SessionLocal
from backend.models import PipelineRun

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()[:64]
    except OSError:
        pass
    return None


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


def begin_pipeline_run(job_key: str, argv_dict: dict[str, Any]) -> int | None:
    """Insert a running row; returns primary key or None if DB unavailable."""
    argv_safe = _json_safe(argv_dict)
    started = datetime.now(timezone.utc)
    hostname = socket.gethostname()
    git = _git_sha()
    try:
        with SessionLocal() as session:
            row = PipelineRun(
                job_key=job_key[:64],
                argv_json=argv_safe,
                started_at=started,
                finished_at=None,
                exit_code=None,
                hostname=hostname[:256],
                git_sha=git,
                detail_json=None,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.id
    except Exception:
        logger.exception("pipeline_run: begin skipped (database unavailable?)")
        return None


def finish_pipeline_run(
    run_id: int | None,
    *,
    exit_code: int,
    detail: dict[str, Any] | None = None,
) -> None:
    if run_id is None:
        return
    finished = datetime.now(timezone.utc)
    detail_safe = _json_safe(detail) if detail else None
    try:
        with SessionLocal() as session:
            row = session.get(PipelineRun, run_id)
            if row is None:
                return
            row.finished_at = finished
            row.exit_code = exit_code
            row.detail_json = detail_safe
            session.commit()
    except Exception:
        logger.exception("pipeline_run: finish failed for run_id=%s", run_id)


def format_argv_for_log(namespace: object) -> dict[str, Any]:
    """Turn argparse.Namespace into JSON-safe dict."""
    raw = vars(namespace)
    return _json_safe(raw)
