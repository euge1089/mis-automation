"""Resolve and tail pipeline log files for the ops UI (no arbitrary path reads)."""

from __future__ import annotations

from pathlib import Path

MAX_TAIL_LINES = 500
MAX_TAIL_BYTES = 600_000

# Cron often redirects to these rolling logs; run_scheduled_pipeline uses logs/scheduler/*.log
JOB_LOG_CANDIDATES: dict[str, list[str]] = {
    "daily-active": ["logs/daily-active.log"],
    "weekly-sold-rented": ["logs/weekly-sold-rented.log"],
    "monthly": ["logs/monthly.log"],
    "load-db": ["logs/load-db.log"],
    "validate-monthly": ["logs/validate-monthly.log"],
    "validate-daily-active": ["logs/validate-daily-active.log"],
    "geocode-active": ["logs/geocode-active.log"],
    "backfill-historical": ["logs/backfill-historical.log"],
}

ALLOWED_JOB_KEYS_FOR_LOGS = frozenset(JOB_LOG_CANDIDATES.keys())


def resolve_log_paths(project_dir: Path, job_key: str) -> list[Path]:
    """Prefer canonical rolling log; fall back to newest matching scheduler fragment."""
    rels = JOB_LOG_CANDIDATES.get(job_key, [])
    for rel in rels:
        p = project_dir / rel
        if p.is_file():
            return [p]

    sched_dir = project_dir / "logs" / "scheduler"
    if sched_dir.is_dir():
        matches = sorted(sched_dir.glob(f"{job_key}_*.log"), key=lambda x: x.stat().st_mtime)
        if matches:
            return [matches[-1]]
    return []


def read_log_tail(project_dir: Path, job_key: str, *, max_lines: int = 400) -> tuple[str | None, str, str | None]:
    """
    Returns ``(absolute_path_str_or_none, tail_text, error_message_or_none)``.
    """
    if job_key not in ALLOWED_JOB_KEYS_FOR_LOGS:
        return None, "", f"Unknown job_key for logs: {job_key!r}"

    ml = min(max(max_lines, 1), MAX_TAIL_LINES)
    paths = resolve_log_paths(project_dir, job_key)
    if not paths:
        return None, "", (
            f"No log file found yet for {job_key!r}. "
            "After jobs run, expect logs under logs/ or logs/scheduler/ in the project folder."
        )

    path = paths[0]
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_TAIL_BYTES:
            raw = raw[-MAX_TAIL_BYTES:]
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        tail = "\n".join(lines[-ml:])
        return str(path.resolve()), tail, None
    except OSError as exc:
        return str(path.resolve()), "", str(exc)
