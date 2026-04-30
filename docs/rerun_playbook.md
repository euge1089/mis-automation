# Safe rerun playbook

Use when you need to re-run a pipeline command without guessing whether data will duplicate.

## Daily active (`daily-active`)

- **Active listings in Postgres** are **fully replaced** on each successful `load_to_db` step (`active_listings` table).
- Running `daily-active` twice with the same underlying exports should produce the **same logical inventory** (same MLS IDs); counts should match unless upstream exports changed.

## Weekly sold/rented (`weekly-sold-rented`)

- Each run re-scrapes the **rolling last three calendar months** and **appends** only new rows into `sold_listing_history` / `rented_listing_history` (skips `(mls_id, event_date, status)` already stored). Re-running the same week without upstream MLS changes should insert **zero** new history rows.
- **`backfill-historical`** still uses **month-window replace** semantics (`memorialize_history_window`) for bulk older fills.
- `sold_analytics_snapshot` after `load-db` matches the latest `sold_clean_latest.csv` for that rolling window.

## Manual `load-db`

- Safe to run repeatedly; it **replaces** analytics snapshot tables (active, rent buckets, sold snapshot) from latest cleaned/analytics files.

## When to worry

- Non-zero exit codes in `/ops/runs`.
- Sudden row-count drops beyond alert thresholds (see `/ops/alerts`).
