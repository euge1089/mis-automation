# Safe rerun playbook

Use when you need to re-run a pipeline command without guessing whether data will duplicate.

## Daily active (`daily-active`)

- **Active listings in Postgres** are **fully replaced** on each successful `load_to_db` step (`active_listings` table).
- Running `daily-active` twice with the same underlying exports should produce the **same logical inventory** (same MLS IDs); counts should match unless upstream exports changed.

## Weekly sold/rented (`weekly-sold-rented`)

- **Memorialization** deletes history rows for each closed month window before re-inserting (`memorialize_history_window`), so reruns for the same window correct data instead of stacking duplicates.
- The **rolling hot-window** CSV outputs refresh each week; `sold_analytics_snapshot` after `load-db` should match the latest `sold_clean_latest.csv`.

## Manual `load-db`

- Safe to run repeatedly; it **replaces** analytics snapshot tables (active, rent buckets, sold snapshot) from latest cleaned/analytics files.

## When to worry

- Non-zero exit codes in `/ops/runs`.
- Sudden row-count drops beyond alert thresholds (see `/ops/alerts`).
