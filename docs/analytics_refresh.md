# Analytics refresh strategy

Sold analytics endpoints (`/sold-area-stats`, `/sold-comps`) read from the Postgres table **`sold_analytics_snapshot`**.

## How it is refreshed

1. The pipeline writes **`cleaned/sold_clean_latest.csv`** during monthly or weekly sold/rented processing.
2. **`python pipeline.py load-db`** (also run at the end of `daily-active` for other tables) loads that CSV into **`sold_analytics_snapshot`** via `load_to_db.load_sold_analytics_snapshot()`.

If `sold_clean_latest.csv` is missing (for example on a machine that only runs daily active), the snapshot step is skipped and the previous snapshot rows are left in place.

## Operational rule

After any workflow that updates sold cleaned data, ensure **`load-db`** runs so the API snapshot matches disk outputs. Scheduled **`weekly-sold-rented`** already invokes **`load_to_db.py`** at the end of the job.
