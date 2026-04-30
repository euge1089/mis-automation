# MLS Automation Pipeline

This project scrapes MLS exports, combines and cleans data, then builds analytics outputs.

It now also includes a database-backed API foundation for your future client application.

## Help for non-technical operators

Step-by-step tasks only **you** can do (logging into GitHub, DigitalOcean, etc.) are in [docs/non_technical_operator_steps.md](docs/non_technical_operator_steps.md).

## Project Direction

This repository is on a transition path:
- current state: MLS scraping is the active listing source for beta analytics testing.
- target state: MLS VOW feed (with photos) becomes the active listing source.

Roadmap detail lives in:
- [docs/project_direction.md](docs/project_direction.md)

## Quick Start

- Optional — local overrides (gitignored):
  - `cp .env.example .env` then edit only if you need custom URLs or MLS login (the app loads `.env` automatically).
- Install dependencies:
  - `python3 -m pip install -r requirements.txt`
  - **Or (npm):** `npm run setup` once (creates `.venv` + installs deps), then `npm run dev`
- Start Postgres/PostGIS:
  - `docker compose up -d db`
- Run monthly pipeline:
  - `python3 pipeline.py monthly`
- Load latest cleaned/analytics data into DB:
  - `python3 pipeline.py load-db`
- Start API:
  - `uvicorn backend.main:app --reload`
- Open API docs:
  - [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Open dashboard UI:
  - [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- Scraper/source quick reference:
  - [docs/scraper_reference.md](docs/scraper_reference.md)
- Architecture principles:
  - [docs/architecture_principles.md](docs/architecture_principles.md)

## End-to-end test (checklist)

Do these in order the first time you validate everything.

**A — Environment**

1. `cd` into this project folder.
2. `python3 -m pip install -r requirements.txt`
3. `docker compose up -d db` then `docker ps` (container `mls-postgis` should be **Up**).

**B — Data pipeline (no scraping)**

Uses CSVs already under `downloads/` and `downloads/rentals/`.

1. `python3 pipeline.py monthly`
2. `python3 pipeline.py validate-monthly` (optional sanity check)

**C — Database + API**

1. `python3 pipeline.py load-db`  
   Expect rent analytics rows loaded; active listings may be **0** until step D.
2. `uvicorn backend.main:app --reload`
3. In the browser: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) → `GET /health` should return `ok`.
4. Try `GET /analytics/rent-by-zip-bedroom` with a `zip_code` you know exists.
5. Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) — rent comps table should populate when you query; active listing table stays empty until step D.

**D — Active listings (optional for first pass)**

Requires `downloads/active/active_export_*.csv` (from your scraper or copied in).

1. `python3 pipeline.py daily-active`  
   If you have no active exports yet, use `python3 pipeline.py daily-active --with-scrape` (needs `.env` MLS credentials and a browser session).
2. Active listings are loaded into Postgres automatically at the end of `daily-active` (unless you pass `--no-load-db`).

**E — Geocoding (optional)**

After `cleaned/active_clean_latest.csv` exists with rows:

1. `python3 pipeline.py geocode-active` (network; can take a while)
2. `python3 pipeline.py load-db`
3. Refresh the dashboard — map markers appear when lat/lon are present.

**F — Full scrape test (optional, slow)**

Only when you are ready for long runs:

- `python3 pipeline.py weekly-sold-rented --headless`
- `python3 pipeline.py daily-active --with-scrape --headless`

## Pipeline Commands

- Monthly historical pipeline (sold + rentals, no scrape):
  - `python3 pipeline.py monthly`
- Monthly historical pipeline including scraping:
  - `python3 pipeline.py monthly --with-scrape`
- Weekly sold/rented MLS refresh with memorialization policy:
  - `python3 pipeline.py weekly-sold-rented --headless`
- One-time historical backfill (default 5 years, month-by-month):
  - `python3 pipeline.py backfill-historical --years 5 --headless --resume`
- Daily active pipeline (no scrape):
  - `python3 pipeline.py daily-active`
- Daily active pipeline including scraping:
  - `python3 pipeline.py daily-active --with-scrape --headless`
- Daily active pipeline + geocoding + DB load:
  - `python3 pipeline.py daily-active --with-scrape --with-geocode`
- Daily active pipeline without DB load (advanced/manual mode):
  - `python3 pipeline.py daily-active --no-load-db`
- Validate monthly outputs only:
  - `python3 pipeline.py validate-monthly`
- Validate daily active outputs only:
  - `python3 pipeline.py validate-daily-active`
- Load data into Postgres:
  - `python3 pipeline.py load-db`
- Geocode active listings only:
  - `python3 pipeline.py geocode-active`

## Scrapers and Data Sources

### MLS scraper entrypoints

- Sold MLS exports:
  - `python3 scrape_mls_sold.py`
- Rentals (rented history) MLS exports:
  - `python3 scrape_mls_rented.py`
- Active/new/price-change/back-on-market MLS exports:
  - `python3 scrape_mls_active.py`
- Optional helper scripts:
  - `python3 mls_result_count.py` (quick MLS result count checks)
  - `python3 scraper_resume.py` / `python3 scraper_adaptive.py` (shared retry/range helpers used by scrapers)

### External sources

- MLS PINergy web app (browser automation via Playwright):
  - used by `scrape_mls_sold.py`, `scrape_mls_rented.py`, `scrape_mls_active.py`
- OpenStreetMap Nominatim geocoding API (enrichment, not listing scrape):
  - used by `geocode_active.py` and `backend/nominatim_geocode.py`

### Scope by scraper

- `scrape_mls_sold.py` (sold):
  - property types: single family, condo, multi-family
  - status: sold
  - timeframe: `TODAY - 1 YEAR`
  - adaptive price-banded exports
- `scrape_mls_rented.py` (rented history):
  - property type: residential rental
  - status: rented
  - timeframe: `TODAY - 1 YEAR`
  - adaptive rent-banded exports
- `scrape_mls_active.py` (inventory + movement):
  - property types: single family, condo, multi-family
  - statuses: active, new, price change, back on market
  - price-banded exports
Geography note: MLS coverage is mostly implicit to the logged-in MLS account and search defaults.

## What the Pipeline Produces

- Latest files:
  - `combined/*.csv`
  - `cleaned/*.csv`
  - `analytics/*.csv`
- Historical snapshots:
  - Monthly sold/rented: `history/monthly/data-YYYY-MM/` after each memorialized month; weekly finish also writes `data-YYYY-MM-rolling/` for the hot-window refresh. Ad-hoc monthly runs use `data-YYYY-MM-monthly-run/`.
  - Daily active: `history/daily_active/YYYY-MM-DD/`

## API Endpoints (v1)

- `GET /health`
- `GET /active-listings`
  - filters: `zip_code`, `town`, `min_price`, `max_price`, `min_beds`, `max_beds`, `limit`
- `GET /map/active-points`
  - simple map payload for active listings
- `GET /analytics/rent-by-zip-bedroom`
  - filters: `zip_code`, `bedrooms`
- `GET /analytics/rent-by-zip-sqft`
  - filters: `zip_code`
- `GET /sold-area-stats`
  - filters: `zip_code`, `town`, `min_beds`, `max_beds`, `property_type`, `months_back`
- `GET /sold-comps`
  - params: `mls_id`, `months_back`
- `POST /geocode/active-listings`
  - body: list of MLS IDs; fills missing lat/lon
- `GET /history/sold`
  - filters: `start_date`, `end_date`, `zip_code`, `limit`
- `GET /history/rented`
  - filters: `start_date`, `end_date`, `zip_code`, `limit`
- `GET /finance/mortgage-presets`
  - illustrative mortgage product presets (same defaults as dashboard UI)
- Ops (pipeline health):
  - `GET /ops` — HTML dashboard (scheduled runs)
  - `GET /ops/runs` — recent `pipeline.py` executions (`limit` query param)
  - `GET /ops/summary` — last successful run per job key
  - `GET /ops/runs/{id}` — single run detail
  - Optional HTTP Basic auth when `OPS_BASIC_AUTH_USER` and `OPS_BASIC_AUTH_PASSWORD` are set in the environment.

## Frontend Dashboard (v1)

- Served by FastAPI at `/`
- Internal ops UI at `/ops` (run history, **listing/file counts per job**, and **log viewer** for rolling server logs; keep behind SSH tunnel or private network, or set Basic auth env vars)
- Includes:
  - active listing search filters
  - listing results table
  - rent comps table by ZIP + bedrooms
  - Leaflet map panel (plots markers when latitude/longitude are available)

## Geocoding Strategy

- The geocoder uses OpenStreetMap Nominatim with a local cache file:
  - `history/geocoding/geocode_cache.csv`
- It retries with cleaner address variants when geocoding fails:
  - full address
  - address with apartment/unit details removed (e.g., `APT`, `UNIT`, `#`)
  - simplified street + town/state/zip variants
- This improves hit rates for condos/apartments with messy unit formatting.

## Database Notes

- The PostGIS image tag used here is `amd64`. On Apple Silicon, Docker runs it under emulation; you may see a platform warning — that is normal.
- **`DATABASE_URL`** is optional on your personal computer when Postgres matches **Docker Compose** defaults (`docker-compose.yml`). The app auto-loads a file named **`.env`** in the project folder if you create one.
- **Production server:** put your real Postgres URL in `.env` as `DATABASE_URL=...` and set **`MLS_PRODUCTION=1`** so the server never accidentally falls back to local defaults.
- Sold analytics endpoints read Postgres table **`sold_analytics_snapshot`** (loaded from `sold_clean_latest.csv` when you run `load-db`). See [docs/analytics_refresh.md](docs/analytics_refresh.md).
- Active listing table is replaced each load with latest daily active snapshot.
- Rent-by-zip-bedroom table is replaced each load from latest analytics output.
- Rent-by-zip-sqft table is replaced each load from latest analytics output.

## Scheduling (cron implemented)

This repo now includes a concrete cron runner:

- wrapper script: `scripts/run_scheduled_pipeline.sh`
- cron template: `infra/cron.example`

Setup:

1. Edit `infra/cron.example` and set `MLS_AUTOMATION_DIR` to your local path.
2. Install entries:
   - `crontab infra/cron.example`
3. Confirm jobs:
   - `crontab -l`

Default scheduled jobs in the template:

- daily active scrape at 2:15am:
  - `daily-active --with-scrape --headless`
- weekly sold/rented scrape and memorialization every Sunday at 3:30am:
  - `weekly-sold-rented --headless`

Note: `daily-active` now includes DB loading by default, so a separate scheduled `load-db` for active freshness is not required.

Hosted recommendation:

- Use a small cloud VM with cron/systemd timers, not a laptop.
- Setup guide: [docs/hosted_scheduler_vm.md](docs/hosted_scheduler_vm.md)

Memorialization policy:

- Each weekly run computes:
  - `memorialize_through = end_of_month(first_day_of_current_month - 3 months)`
- Closed months at or before that cutoff are memorialized to historical DB tables.
- Current analytics window is re-scraped from `memorialize_through + 1 day` through today.

Example:

- On `2026-04-29`, memorialize through `2025-12-31`.
- Re-scrape hot window from `2026-01-01` through current date.

## Notes

- Validation checks are built in and will fail the run when critical output quality issues are detected.
- Scrapers depend on `.env` containing:
  - `MLS_USERNAME`
  - `MLS_PASSWORD`
- Daily active scraping expects active export files in `downloads/active/` if you do not use `--with-scrape`.
