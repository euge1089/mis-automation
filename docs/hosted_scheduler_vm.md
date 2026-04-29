# Hosted Scheduler (Cloud VM)

Recommended for this repo: a small Linux VM with cron or systemd timers.

## Why VM

- Stable disk for `downloads/`, `history/`, and logs.
- Works well with long-running Playwright jobs.
- Easy secret/env management and predictable scheduling.

## Provision Checklist

1. Install Python 3.12+, pip, and Chromium deps required by Playwright.
2. Clone repo and create venv:
   - `python3 -m venv .venv`
   - `.venv/bin/pip install -U pip`
   - `.venv/bin/pip install -r requirements.txt`
3. Install Playwright browser:
   - `.venv/bin/python -m playwright install chromium`
4. Configure env:
   - `MLS_USERNAME`
   - `MLS_PASSWORD`
   - `DATABASE_URL`
5. Verify commands:
   - `.venv/bin/python pipeline.py weekly-sold-rented --headless --no-scrape`
   - `.venv/bin/python pipeline.py daily-active --with-scrape --headless`

## Suggested Schedule

- Weekly sold/rented:
  - `bash scripts/run_scheduled_pipeline.sh weekly-sold-rented --headless`
- Daily active:
  - `bash scripts/run_scheduled_pipeline.sh daily-active --with-scrape --headless`

Template cron entries are in `infra/cron.example`.
