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

## Firewall (UFW)

Recommended on Ubuntu: allow SSH only; Postgres stays on `127.0.0.1` (see `docker-compose.yml`), so **do not** open port 5432 publicly.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp comment SSH
# Optional: only if you intentionally expose the API without a tunnel
# sudo ufw allow 8000/tcp comment MLS-API
sudo ufw --force enable
sudo ufw status verbose
```

Confirm you can open a **new** SSH session before closing the current one.

## Postgres backups

Use `scripts/backup_postgres.sh` (defaults: container `mls-postgis`, DB `mls_analytics`, backups under `/opt/backups/mls`, 14-day retention).

```bash
sudo chmod +x /opt/mls-automation/scripts/backup_postgres.sh
sudo PGPASSWORD=mls_pass BACKUP_ROOT=/opt/backups/mls /opt/mls-automation/scripts/backup_postgres.sh
```

Schedule root cron (example 07:15 UTC daily):

```cron
15 7 * * * PGPASSWORD=mls_pass /opt/mls-automation/scripts/backup_postgres.sh >> /opt/mls-automation/logs/backup.log 2>&1
```

Copy dumps off-droplet periodically (S3, another region, or encrypted storage).
