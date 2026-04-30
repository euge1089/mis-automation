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
4. Configure a file named **`.env`** in the project folder (same level as `README.md`). The pipeline and API load it automatically. Include at least:
   - `MLS_USERNAME`
   - `MLS_PASSWORD`
   - If Postgres on that machine matches Docker Compose defaults, you can omit `DATABASE_URL`.
   - If Postgres uses a non-default URL or host, set `DATABASE_URL=...` and add **`MLS_PRODUCTION=1`** so the app never falls back to local defaults.
5. Verify commands:
   - `.venv/bin/python pipeline.py weekly-sold-rented --headless --no-scrape`
   - `.venv/bin/python pipeline.py daily-active --with-scrape --headless`

## Suggested Schedule

- Weekly sold/rented:
  - `bash scripts/run_scheduled_pipeline.sh weekly-sold-rented --headless`
- Daily active:
  - `bash scripts/run_scheduled_pipeline.sh daily-active --with-scrape --headless`

`daily-active` loads cleaned outputs into Postgres by default (use `--no-load-db` only for manual/troubleshooting runs).

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

## Tomorrow-ready deploy (`/opt/mls-automation`)

What cron actually runs is **`scripts/run_scheduled_pipeline.sh`** from **`MLS_AUTOMATION_DIR`** (usually **`/opt/mls-automation`**). Each **`daily-active --with-scrape`** run **deletes** prior **`downloads/active/active_export_*.csv`** slices, then scrapes fresh MLS exports (then combine → clean → validate → DB load).

1. **Ship code to the VM’s deploy folder** (from your laptop, repo root):  
   `rsync -az --exclude '.venv' --exclude '.git' --exclude '.env' --exclude 'downloads' --exclude 'history' --exclude 'logs' ./ mlsops@YOUR_DROPLET:~/mls-automation-deploy/`
2. **Merge into `/opt` and restart the API** (run **on the VM**, needs sudo once):  
   `sudo bash ~/mls-automation-deploy/infra/vm_merge_deploy.sh`  
   This runs **`pip install`**, **`playwright install chromium`**, and **`systemctl restart mls-api.service`**.

If **`systemctl`** says **`Result=resources`** or the unit never reaches **active**, systemd may have **hit its start burst limit** (default is only a few fast restarts per 10 seconds — common right after a bad deploy). On the VM:

```bash
sudo systemctl stop mls-api.service
sudo systemctl reset-failed mls-api.service
sudo cp /opt/mls-automation/infra/mls-api.service /etc/systemd/system/mls-api.service   # first time: install relaxed limits from repo
sudo systemctl daemon-reload
sudo systemctl start mls-api.service
sudo systemctl status mls-api.service --no-pager
curl -s http://127.0.0.1:8000/health
```

(`infra/mls-api.service` in the repo widens **`StartLimitBurst`** / **`StartLimitIntervalSec`** so upgrades are less fragile.)
3. **Match production cron** to **`infra/crontab.production.opt.txt`** (`crontab -e` as **`mlsops`**): daily **`daily-active --with-scrape --headless`** at **`02:15`**, weekly **`weekly-sold-rented --headless`** as you prefer.
4. **Smoke test** (optional):  
   `cd /opt/mls-automation && bash scripts/run_scheduled_pipeline.sh daily-active --with-scrape --headless`  
   Log: **`logs/scheduler/daily-active_*.log`**.

## Production ops VM (reference)

These details match the **DigitalOcean** droplet used for schedules, API, and deploys. **Confirm in the dashboard** before relying on them—recreating or migrating a droplet **changes the public IP**.

| Field | Value |
| --- | --- |
| **Droplet name** | `mls-ops-1` |
| **Region / image** | NYC1 · Ubuntu 24.04 LTS x64 (example size: 4 GB RAM / 80 GB disk) |
| **Public IPv4** | `142.93.202.226` |
| **SSH user** | `mlsops` |
| **App directory** | `/opt/mls-automation` |
| **Pre-merge deploy bundle** (rsync target from laptop) | `~/mls-automation-deploy/` on the VM |

After rsync, merge into `/opt` and restart the API: `infra/vm_merge_deploy.sh` (run **on the VM**).

**Browser access:** the API usually listens on `127.0.0.1:8000` on the VM—use an **SSH tunnel** from your computer (`ssh -L 8000:127.0.0.1:8000 mlsops@142.93.202.226`) then open `http://127.0.0.1:8000/ops` unless you expose the port another way.

**Cron checklist (production):** `crontab` is **not** in this repo. Confirm `pipeline.py daily-active` includes **`--with-scrape`** (and usually `--headless`); omitting `--with-scrape` means **no MLS scrape**—only existing CSVs. Weekly defaults to scraping unless **`--no-scrape`** is set. After edits run `crontab -l` to verify.

Full alignment notes (scraping risk, `/ops` metrics, `--headless`): [mls_scraping_and_ops_alignment.md](mls_scraping_and_ops_alignment.md).
