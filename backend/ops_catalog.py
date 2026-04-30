"""Plain-language copy for the ops dashboard (non-technical readers)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobHelp:
    title: str
    one_liner: str
    what_it_does: str
    success_means: str
    schedule_hint: str


JOB_HELP: dict[str, JobHelp] = {
    "daily-active": JobHelp(
        title="Daily active listings refresh",
        one_liner="Updates the list of homes currently for sale from MLS.",
        what_it_does=(
            "Pulls the latest active listing exports from MLS (when scraping is on), merges them, "
            "cleans the data, checks basic quality, and saves a dated snapshot for history."
        ),
        success_means=(
            "You should see thousands of active listings after cleaning (exact count varies by market). "
            "If scraping ran, raw export files were downloaded first; then combined and cleaned counts appear below."
        ),
        schedule_hint="Usually runs once every morning (cron).",
    ),
    "weekly-sold-rented": JobHelp(
        title="Weekly sold & rented refresh",
        one_liner="Keeps sold/rent history current and loads analytics into the database.",
        what_it_does=(
            "Clears prior raw sold/rent CSV downloads (when scraping), pulls MLS for the rolling last "
            "three calendar months, rebuilds rent-by-ZIP models, validates outputs, appends only "
            "new sold/rent rows into long-term history tables, loads analytics into the database, "
            "and saves a snapshot."
        ),
        success_means=(
            "Sold and rental cleaned files have many rows; rent models have enough ZIP buckets; "
            "database load completes without errors."
        ),
        schedule_hint="Usually weekly (e.g. Sunday morning).",
    ),
    "monthly": JobHelp(
        title="Monthly historical pipeline",
        one_liner="Full sold + rentals processing (optional scrape).",
        what_it_does=(
            "Combines sold/rental exports, cleans them, builds rent models, validates, and saves a monthly snapshot folder."
        ),
        success_means="All required CSVs exist, row counts look healthy, and validation prints success.",
        schedule_hint="Run manually or on a schedule if you use this instead of weekly.",
    ),
    "backfill-historical": JobHelp(
        title="Historical backfill",
        one_liner="Fills in many months of sold/rent history into the memorialized tables.",
        what_it_does=(
            "Walks month windows (optionally scraping each), memorializes each window into Postgres, "
            "and advances checkpoints so you can resume."
        ),
        success_means="Each window completes; checkpoint files update; no repeated failures.",
        schedule_hint="Typically one-time or rare maintenance.",
    ),
    "validate-monthly": JobHelp(
        title="Monthly output check",
        one_liner="Sanity-check that sold/rent/analytics files exist and look reasonable.",
        what_it_does="Reads your combined/cleaned/analytics CSVs and applies rule checks (non-empty files, ZIP quality, minimum rent-model rows).",
        success_means='You see "Monthly data quality checks passed" in logs and exit code 0.',
        schedule_hint="Optional manual spot-check.",
    ),
    "validate-daily-active": JobHelp(
        title="Daily active output check",
        one_liner="Sanity-check that the cleaned active listing file exists and has rows.",
        what_it_does="Confirms active_clean_latest.csv is present and passes basic checks.",
        success_means='You see "Daily active data quality checks passed."',
        schedule_hint="Optional manual spot-check.",
    ),
    "load-db": JobHelp(
        title="Load database",
        one_liner="Pushes cleaned CSVs and analytics into Postgres for the API.",
        what_it_does="Rebuilds analytics tables and active listings from current cleaned files.",
        success_means="Counts print for active listings and rent models; API reflects fresh data.",
        schedule_hint="Often at the end of weekly pipeline or after manual runs.",
    ),
    "geocode-active": JobHelp(
        title="Geocode active addresses",
        one_liner="Fills in latitude/longitude for listings missing coordinates.",
        what_it_does="Calls the geocoder with caching; updates your cleaned active data path used by maps.",
        success_means="Geocode completes without fatal errors; map pins improve on next load.",
        schedule_hint="Optional after large active refreshes.",
    ),
}


ALERT_COPY = {
    "slack": (
        "If Slack is configured on the server, critical failures can send a short message to your channel. "
        "You can still use this dashboard as the main place to review history."
    ),
    "active_drop": (
        "We can warn if active listings drop sharply versus the previous successful run—often that means "
        "a scrape problem or MLS change, not a real market crash in one day."
    ),
    "sold_rent_min": (
        "Sold/rent analytics rows below a minimum may indicate incomplete scraping or a bad combine step."
    ),
}


def help_for(job_key: str) -> JobHelp:
    return JOB_HELP.get(
        job_key,
        JobHelp(
            title=job_key.replace("-", " ").title(),
            one_liner="Pipeline command.",
            what_it_does="Runs part of the MLS automation pipeline.",
            success_means="Process exited with code 0.",
            schedule_hint="See your server cron or runbook.",
        ),
    )
