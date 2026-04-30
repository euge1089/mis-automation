"""Boundary between MLS ingestion mechanisms and normalized downstream pipeline inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class ActiveListingSource(Protocol):
    """
    Produces raw MLS active exports under ``downloads/active/`` (current pipeline contract).

    Future: VOW adapter writes normalized rows or staging tables instead; downstream cleaning stays stable.
    """

    name: str

    def run_export(self, *, project_dir: Path, headless: bool) -> None:
        """Fetch/update exports for the active listing pipeline."""
        ...


class ScraperActiveListingSource:
    """Adapter for Playwright-based ``scrape_mls_active.py`` (implementation stays in repo root)."""

    name = "mls_pinergy_scraper"

    def run_export(self, *, project_dir: Path, headless: bool) -> None:
        import subprocess
        import sys

        cmd = [sys.executable, str(project_dir / "scrape_mls_active.py")]
        if headless:
            cmd.append("--headless")
        subprocess.run(cmd, check=True, cwd=project_dir)


class VowFeedActiveListingSource:
    """Placeholder for MLS VOW feed ingestion (no production wiring yet)."""

    name = "mls_vow_feed"

    def run_export(self, *, project_dir: Path, headless: bool) -> None:
        raise NotImplementedError("VOW adapter: implement when feed credentials and schema are available.")
