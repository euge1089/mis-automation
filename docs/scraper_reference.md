# Scraper Reference

This is the quick reference for what is scraped, from where, and with what scope.

## Transitional Role

- `scrape_mls_active.py` is the current active listing source for beta analytics testing.
- Planned replacement: MLS VOW feed adapter (with listing photos/media support).
- Until VOW access is available, active MLS scraping remains in place and should continue daily.

## Sources Being Scraped

- MLS PINergy web app (Playwright browser automation):
  - `scrape_mls_sold.py`
  - `scrape_mls_rented.py`
  - `scrape_mls_active.py`
- OpenStreetMap Nominatim geocoding API (enrichment, not listing scrape):
  - `geocode_active.py`
  - `backend/nominatim_geocode.py`

## Scope By Scraper

- `scrape_mls_sold.py`:
  - property types: single family, condo, multi-family
  - status: sold
  - timeframe: configurable with `--timeframe`
  - adaptive price-banded exports
- `scrape_mls_rented.py`:
  - property type: residential rental
  - status: rented
  - timeframe: configurable with `--timeframe`
  - adaptive rent-banded exports
- `scrape_mls_active.py`:
  - property types: single family, condo, multi-family
  - statuses: active, new, price change, back on market
  - adaptive price-banded exports
  - role in roadmap: transitional active source prior to VOW integration

Geography note: MLS coverage is driven by account/search access in PINergy.

## Output Files

- Sold exports: `downloads/mls_export_*.csv`
- Rented exports: `downloads/rentals/rentals_export_*.csv`
- Active exports: `downloads/active/active_export_*.csv`
- Combined: `combined/*.csv`
- Cleaned: `cleaned/*.csv`
- Analytics: `analytics/*.csv`
- History snapshots/checkpoints: `history/`

## Operational Notes

- MLS export cap can interrupt long runs; use resume-friendly ranges and stagger workloads.
- Scheduled hosted runs should use non-interactive mode (default) and usually `--headless`.
- `pipeline.py backfill-historical` handles one-time 5-year monthly backfill with checkpoints.
- `pipeline.py weekly-sold-rented` applies rolling policy:
  - memorialize closed months through the 3-month lag cutoff
  - refresh hot window (cutoff+1 day through today)
