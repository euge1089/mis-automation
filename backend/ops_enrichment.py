"""Turn DB rows + metrics into plain-language strings for the ops UI."""

from __future__ import annotations

from backend.models import PipelineRun
from backend.ops_catalog import help_for


def _scrape_mode_hint(job_key: str, argv_json: dict | list | None) -> str | None:
    if not isinstance(argv_json, dict):
        return None
    if job_key == "daily-active":
        if argv_json.get("with_scrape"):
            return "Run mode: live MLS browser scraping was ON (--with-scrape)."
        return "Run mode: used CSV files already in downloads/active (no browser scrape in this command)."
    if job_key == "weekly-sold-rented":
        if argv_json.get("no_scrape"):
            return "Run mode: sold/rented scraping was OFF (--no-scrape); existing downloads were processed."
        return "Run mode: sold/rented scraping was ON (exports refreshed before combine)."
    return None


def _duration_line(detail: dict) -> str | None:
    v = detail.get("duration_seconds")
    if not isinstance(v, (int, float)):
        return None
    sec = float(v)
    if sec >= 3600:
        return f"Wall-clock duration: {sec / 3600:.2f} hours ({sec:,.0f} seconds)."
    if sec >= 60:
        return f"Wall-clock duration: {sec / 60:.1f} minutes ({sec:,.0f} seconds)."
    return f"Wall-clock duration: {sec:.1f} seconds."


def metric_lines(job_key: str, detail: dict | None, argv_json: dict | list | None = None) -> list[str]:
    lines: list[str] = []
    hint = _scrape_mode_hint(job_key, argv_json)
    if hint:
        lines.append(hint)

    if detail is None:
        return [ln for ln in lines if ln]

    d = detail
    if dur := _duration_line(d):
        lines.append(dur)

    def fmt_int(k: str, label: str) -> None:
        v = d.get(k)
        if isinstance(v, bool):
            lines.append(f"{label}: {'yes' if v else 'no'}")
        elif isinstance(v, int):
            lines.append(f"{label}: {v:,}")
        elif isinstance(v, float) and v == int(v):
            lines.append(f"{label}: {int(v):,}")

    if job_key == "daily-active":
        # Scrape/download signals first (highest operational risk); downstream counts after.
        fmt_int(
            "raw_mls_export_files",
            "MLS scrape: number of active_export_*.csv slice files in downloads/active",
        )
        fmt_int(
            "active_export_rows_raw_sum",
            "MLS scrape: ≈ raw listing rows across those slices before combine (bands can overlap)",
        )
        fmt_int("active_listings_combined_rows", "After combine: rows in combined/active_latest.csv (deduped)")
        fmt_int(
            "active_listings_after_cleaning",
            "After cleaning: rows in active_clean_latest.csv (validation & loads)",
        )
        fmt_int("active_listings_in_database", "Active listing rows in Postgres after load-db")
        fmt_int("sold_analytics_snapshot_rows", "Sold analytics snapshot rows in Postgres (if load-db ran)")

    elif job_key in ("weekly-sold-rented", "monthly", "validate-monthly"):
        fmt_int("sold_export_files", "MLS scrape: sold export CSV files (downloads/mls_export_*.csv)")
        fmt_int("rentals_export_files", "MLS scrape: rental export CSV files (downloads/rentals/)")
        fmt_int(
            "sold_export_rows_raw_sum",
            "MLS scrape: ≈ raw sold rows across downloaded exports (before downstream combine)",
        )
        fmt_int(
            "rentals_export_rows_raw_sum",
            "MLS scrape: ≈ raw rental rows across downloaded exports",
        )
        fmt_int("sold_rows_combined", "Sold rows (combined)")
        fmt_int("rentals_rows_combined", "Rental rows (combined)")
        fmt_int("sold_rows_cleaned", "Sold rows (cleaned)")
        fmt_int("rentals_rows_cleaned", "Rental rows (cleaned)")
        fmt_int("rent_zip_bedroom_buckets", "Rent-by-ZIP-bedroom buckets")
        fmt_int("rent_zip_sqft_buckets", "Rent-by-ZIP-sqft buckets")
        fmt_int("sold_analytics_snapshot_rows", "Sold analytics snapshot rows in Postgres")

    elif job_key == "validate-daily-active":
        fmt_int("active_listings_after_cleaning", "Active listings in cleaned file")

    elif job_key == "load-db":
        fmt_int("active_listings_in_database", "Active listings stored in database")
        fmt_int("sold_analytics_snapshot_rows", "Sold analytics snapshot rows in Postgres")
        if note := d.get("database_note"):
            lines.append(str(note))
        if note := d.get("database_metrics_note"):
            lines.append(str(note))

    return [ln for ln in lines if ln]


def success_message(run: PipelineRun) -> str:
    h = help_for(run.job_key)
    if run.exit_code == 0:
        return f"Success — {h.success_means}"
    if run.exit_code is None:
        return "Status incomplete (run may have been interrupted)."
    err = ""
    if run.detail_json and isinstance(run.detail_json, dict):
        err = run.detail_json.get("error") or ""
    err_bit = f" Details: {err}" if err else ""
    return f"This run did not finish OK (exit code {run.exit_code}).{err_bit}"


def headline_status(run: PipelineRun) -> str:
    if run.exit_code == 0:
        return "Completed successfully"
    if run.exit_code is None:
        return "Incomplete"
    return "Failed or stopped with an error"


def error_summary(run: PipelineRun) -> str | None:
    """One-line error from ``detail_json`` for failed runs (truncated for UI)."""
    if run.exit_code == 0 or run.exit_code is None:
        return None
    detail = run.detail_json if isinstance(run.detail_json, dict) else {}
    err = detail.get("error")
    if err is None or err == "":
        return None
    s = str(err).strip()
    if len(s) > 400:
        return s[:397] + "..."
    return s


def build_ops_run_row(run: PipelineRun) -> dict[str, object]:
    h = help_for(run.job_key)
    detail = run.detail_json if isinstance(run.detail_json, dict) else {}
    argv_j = run.argv_json if isinstance(run.argv_json, dict) else None
    return {
        "id": run.id,
        "job_key": run.job_key,
        "title": h.title,
        "one_liner": h.one_liner,
        "what_it_does": h.what_it_does,
        "schedule_hint": h.schedule_hint,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "exit_code": run.exit_code,
        "hostname": run.hostname,
        "git_sha": run.git_sha,
        "headline_status": headline_status(run),
        "success_message": success_message(run),
        "metric_lines": metric_lines(run.job_key, detail, argv_j),
        "detail_json": run.detail_json,
        "argv_json": run.argv_json,
        "error_summary": error_summary(run),
    }
