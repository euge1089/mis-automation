"""Resolve and tail pipeline log files for the ops UI (no arbitrary path reads)."""

from __future__ import annotations

from pathlib import Path

MAX_TAIL_LINES = 500
MAX_TAIL_BYTES = 600_000
# Scan at most this many bytes when extracting a run-scoped excerpt (tail-biased for large logs).
MAX_EXCERPT_SCAN_BYTES = 4 * 1024 * 1024

ANCHOR_PREFIX = "PIPELINE_RUN_LOG_ANCHOR"

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


def read_run_log_excerpt(
    project_dir: Path,
    job_key: str,
    run_id: int,
    *,
    max_lines: int = 200,
) -> tuple[str | None, str, str | None]:
    """
    Return log lines for one pipeline run using ``PIPELINE_RUN_LOG_ANCHOR id=<run_id>`` markers.

    Returns ``(resolved_path_or_none, excerpt_text, note_or_none)``.
    For large files, only the last ``MAX_EXCERPT_SCAN_BYTES`` bytes are searched.
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
    note_parts: list[str] = []
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_EXCERPT_SCAN_BYTES:
            raw = raw[-MAX_EXCERPT_SCAN_BYTES:]
            note_parts.append(
                "Log file is large; only the last portion was scanned for this run's marker."
            )
        text = raw.decode("utf-8", errors="replace")
    except OSError as exc:
        return str(path.resolve()), "", str(exc)

    lines = text.splitlines()
    needle = f"{ANCHOR_PREFIX} id={run_id}"
    start_idx: int | None = None
    for i, line in enumerate(lines):
        if needle in line:
            start_idx = i
            break

    if start_idx is None:
        note_parts.append(
            "No log marker found for this run id. Runs from before the anchor was added, "
            "or markers outside the scanned portion of the file, won't show an excerpt here."
        )
        return str(path.resolve()), "", " ".join(note_parts) if note_parts else None

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        if ANCHOR_PREFIX in lines[j] and f"id={run_id}" not in lines[j]:
            end_idx = j
            break

    chunk = lines[start_idx:end_idx]
    if len(chunk) > ml:
        chunk = chunk[:ml]
        note_parts.append(f"Excerpt trimmed to {ml} lines.")

    excerpt = "\n".join(chunk)
    note = " ".join(note_parts) if note_parts else None
    return str(path.resolve()), excerpt, note
