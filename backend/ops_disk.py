"""Disk usage for the ops dashboard (project root only; bounded subprocess calls)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


MAX_DU_TIMEOUT_SEC = 1.5
ALLOWED_SUBDIRS = frozenset({"downloads", "history", "logs"})


def du_one_dir(path: Path, *, timeout_sec: float = MAX_DU_TIMEOUT_SEC) -> int | None:
    """Return byte size of directory via ``du -sb``, or None on failure."""
    if not path.is_dir():
        return None
    try:
        out = subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if out.returncode != 0 or not out.stdout:
            return None
        first = out.stdout.strip().split()[0]
        return int(first)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def disk_usage_snapshot(project_dir: Path) -> dict[str, object]:
    """
    Filesystem stats for ``project_dir`` plus sizes of allowlisted subfolders.

    Never walks arbitrary trees from Python; ``du`` is bounded by timeout.
    """
    project_dir = project_dir.resolve()
    usage = shutil.disk_usage(project_dir)
    total, used, free = usage.total, usage.used, usage.free
    pct = round(100.0 * used / total, 1) if total else 0.0
    heavy: dict[str, int | None] = {}
    for name in sorted(ALLOWED_SUBDIRS):
        heavy[name] = du_one_dir(project_dir / name)
    return {
        "project_path": str(project_dir),
        "filesystem_total_bytes": total,
        "filesystem_used_bytes": used,
        "filesystem_free_bytes": free,
        "filesystem_used_pct": pct,
        "heavy_dirs_bytes": heavy,
    }


def linux_loadavg_line() -> str | None:
    """Return first line of ``/proc/loadavg`` on Linux, else None."""
    path = Path("/proc/loadavg")
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0]
    except OSError:
        return None


def extended_host_metrics_if_enabled() -> dict[str, str] | None:
    """Optional extra metrics when ``OPS_EXTENDED_METRICS=1`` (Linux load average)."""
    if os.environ.get("OPS_EXTENDED_METRICS", "").strip() != "1":
        return None
    load = linux_loadavg_line()
    if not load:
        return None
    return {"loadavg": load}
