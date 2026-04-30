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


def metric_lines(job_key: str, detail: dict | None, argv_json: dict | list | None = None) -> list[str]:
    lines: list[str] = []
    hint = _scrape_mode_hint(job_key, argv_json)
    if hint:
        lines.append(hint)

    if not detail:
        return [ln for ln in lines if ln]

    d = detail

    def fmt_int(k: str, label: str) -> None:
        v = d.get(k)
        if isinstance(v, bool):
            lines.append(f"{label}: {'yes' if v else 'no'}")
        elif isinstance(v, int):
            lines.append(f"{label}: {v:,}")
        elif isinstance(v, float) and v == int(v):
            lines.append(f"{label}: {int(v):,}")

    if job_key == "daily-active":
        fmt_int("raw_mls_export_files", "MLS export CSV files in downloads/active (input slices)")
        fmt_int("active_listings_combined_rows", "Rows in combined/active_latest.csv (merged from all slices)")
        fmt_int(
            "active_listings_after_cleaning",
            "Listings after cleaning (active_clean_latest.csv — used for validation & loads)",
        )
        fmt_int("active_listings_in_database", "Active listing rows in Postgres after load-db step")
        fmt_int("sold_analytics_snapshot_rows", "Sold analytics snapshot rows in Postgres (if load-db ran)")

    elif job_key in ("weekly-sold-rented", "monthly", "validate-monthly"):
        fmt_int("sold_export_files", "Sold MLS export CSV files in downloads/ (mls_export_*.csv)")
        fmt_int("rentals_export_files", "Rental export CSV files in downloads/rentals/")
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
    }
