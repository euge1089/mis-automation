"""Read Postgres backup heartbeat file written by ``scripts/backup_postgres.sh``."""

from __future__ import annotations

import os
from pathlib import Path

from backend.schemas import OpsBackupStatusOut


def read_backup_status(project_dir: Path) -> OpsBackupStatusOut:
    """
    Load status from ``OPS_BACKUP_HEARTBEAT_PATH`` or common defaults.

    The backup script writes one ISO-8601 UTC line on success.
    """
    project_dir = project_dir.resolve()
    candidates: list[Path] = []
    env = os.environ.get("OPS_BACKUP_HEARTBEAT_PATH", "").strip()
    if env:
        candidates.append(Path(env))
    candidates.append(Path("/opt/backups/mls/.last_backup_heartbeat"))
    candidates.append(project_dir / "logs" / ".backup_heartbeat")

    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return OpsBackupStatusOut(
            status="unknown",
            message=(
                "No backup heartbeat file found yet. "
                "After nightly backups run, a timestamp file appears (see OPS_BACKUP_HEARTBEAT_PATH)."
            ),
            heartbeat_path=None,
            last_backup_utc=None,
        )

    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        first_line = raw.splitlines()[0].strip() if raw else ""
    except OSError as exc:
        return OpsBackupStatusOut(
            status="unknown",
            message=f"Could not read heartbeat file: {exc}",
            heartbeat_path=str(path.resolve()),
            last_backup_utc=None,
        )

    return OpsBackupStatusOut(
        status="ok",
        message="A recent backup run recorded a heartbeat (UTC timestamp below).",
        heartbeat_path=str(path.resolve()),
        last_backup_utc=first_line or None,
    )
