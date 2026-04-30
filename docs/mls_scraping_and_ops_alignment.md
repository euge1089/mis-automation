# MLS scraping, ops alignment, and what the dashboard shows

This document keeps **everyone aligned** on where things break most often, how **production schedules** must be configured, and how **`/ops`** reports runs.

## Where jobs usually fail (risk order)

1. **MLS web scraping** — Playwright logs into MLS Pinergy, applies filters, downloads CSV **slices** (price bands, etc.). Failures here: login expired, MLS UI changes, timeouts, rate limits, headless/browser deps missing on the server.
2. **Combine / clean / load** — Deterministic steps on files already on disk. Easier to debug because outputs are plain CSVs and logs.

**Implication:** Scheduled **`cron`** lines and **`/ops`** metrics should make it **obvious whether scraping ran** and give **strong signals from raw downloads**, not only final combined row counts.

## Production cron (cannot drift silently)

- **`crontab` lives only on the server** — it is not in Git. A wrong line can run for months while the app “looks fine” because it still merges old files.
- **`daily-active` must include `--with-scrape`** for fresh MLS downloads. Otherwise the job only runs `combine` on whatever is already under `downloads/active/`.  
  - Correct pattern: `pipeline.py daily-active --with-scrape --headless`  
  - Template: `infra/cron.example`  
- **`weekly-sold-rented`** scrapes **by default**. The dangerous flag is **`--no-scrape`**, which skips fresh sold/rental exports.

After any server change, run `crontab -l` and compare to `infra/cron.example` (or this doc).

`pipeline.py` prints a **WARNING to stderr** if `daily-active` runs without `--with-scrape` or if `weekly-sold-rented` runs with `--no-scrape`.

## What `--headless` means (and when you need it)

- **`--headless`** tells Playwright to run **Chromium without opening a visible browser window**.
- **Required for cron / systemd on a Linux VM** that has no graphical desktop attached to the session.
- **Optional on your Mac** when you want to watch the browser for debugging (omit `--headless`); behavior against MLS is the same.
- It does **not** replace **`--with-scrape`** — headless only affects visibility of the browser, not whether scraping runs.

## What `/ops` and run metrics emphasize

For each pipeline run, stored **`detail_json`** (from `backend/run_metrics.py`) includes:

### Daily active (`daily-active`)

| Metric (stored key) | Meaning |
| --- | --- |
| Run mode | From argv: `--with-scrape` vs CSV-only (shown as plain English on cards). |
| **`raw_mls_export_files`** | Count of `active_export_*.csv` slice files under `downloads/active/` after the run (proxy for “how many downloads/chunks”). |
| **`active_export_rows_raw_sum`** | Sum of **data rows** across those raw slices (**before** `combine` dedupes). Slices can overlap; this is a **volume signal**, not duplicate deduped listings. |
| **`active_listings_combined_rows`** | Rows in `combined/active_latest.csv` after dedupe. |
| **`active_listings_after_cleaning`** | Rows after cleaning. |
| **`active_listings_in_database`** | Postgres after load (when load-db ran). |

### Weekly sold/rented (`weekly-sold-rented`)

| Metric | Meaning |
| --- | --- |
| **`sold_export_files`** / **`rentals_export_files`** | Count of raw export CSVs on disk in each folder. |
| **`sold_export_rows_raw_sum`** / **`rentals_export_rows_raw_sum`** | Sum of data rows across those files (volume before downstream combine). |
| Cleaned / combined / analytics row counts | Downstream of downloads. |

**Why both file counts and raw row sums:** File counts show **how many separate MLS downloads** completed; raw row sums show **rough volume** from those files. Final combined/cleaned counts are what feed the app but **lag insight into scrape health**.

## Operator checklist (weekly)

1. Open **`/ops`** → Recent runs → confirm **“live MLS browser scraping was ON”** for scheduled daily runs (and no accidental `--no-scrape` on weekly if you expect fresh data).
2. Check **raw slice counts / raw row sums** on the latest runs for jumps to zero or absurd drops vs prior runs.
3. If something looks wrong, open **“Log lines for this run”** or the rolling log — scrape failures usually show there before combine.

## Database: current active listings are fully replaced (no stale rows)

Each load **deletes every row** in **`active_listings`** and re-inserts from **`cleaned/active_clean_latest.csv`**. Homes that are no longer active **disappear from Postgres**—they are not kept as stale noise.

## Raw active CSV slices: cleared before each daily scrape

For **`daily-active` with `--with-scrape`**, **`pipeline.py`** removes **`downloads/active/active_export_*.csv`** **before** the scraper runs (`storage_paths.clear_active_raw_downloads`). Each run starts **without** prior-day slice files, then pulls **fresh** MLS exports for that run (subject to MLS caps). Combine-only runs (**no** `--with-scrape`) do **not** clear that folder.

## When the active scraper says “nothing to do”

Rare after the pre-scrape clear: it means the scraper believes **no bands** need downloads (misconfiguration or edge case). **`--from-start`** still forces the scraper’s ignore-resume mode if you need it for troubleshooting.

## Related files

- `infra/cron.example` — canonical scheduled commands  
- `scripts/run_scheduled_pipeline.sh` — wrapper used by some installs  
- `storage_paths.py` — `clear_active_raw_downloads`, sold/rent clears  
- `backend/run_metrics.py` — collects post-run file/row counts  
- `backend/ops_enrichment.py` — plain-language lines on `/ops`  
- `docs/non_technical_operator_steps.md` — how to inspect `crontab` on the VM  
