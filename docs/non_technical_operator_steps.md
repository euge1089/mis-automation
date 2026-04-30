# What you do yourself (plain-language steps)

This project already loads settings from a file named **`.env`** in the project folder. You do **not** need to understand “machines” to use your **Mac** day to day: open Cursor, run the app, use the browser. The steps below are only for **accounts you log into in a browser** (GitHub, DigitalOcean, etc.) or **one cloud computer** (the small Linux server that runs scheduled jobs).

**Canonical guide (scraping, cron flags, what `/ops` shows):** [mls_scraping_and_ops_alignment.md](mls_scraping_and_ops_alignment.md)

Words you might see:

- **VM (“droplet”)**: a rented Linux computer in the cloud that runs your scheduled MLS jobs 24/7.
- **SSH**: a secure way to open a **terminal session on that server** from your Mac (Cursor can do this, or DigitalOcean gives you a browser console).
- **Cron**: the server’s alarm clock that runs `daily-active` / `weekly-sold-rented` on a schedule.

---

## A. Confirm the scheduler on your cloud server (production crontab)

**Goal:** The server runs daily + weekly MLS jobs and backups on a schedule you expect.

### Can Cursor / an agent do this for you?

**Often yes, on your Mac.** If your Mac already has SSH keys set up (no password prompt when connecting), an agent can run the same terminal commands you would run and paste the results back to you. That only works when:

- The droplet’s IP or hostname is known (for example from DigitalOcean, or from `~/.ssh/known_hosts` after you’ve connected once), and  
- SSH accepts your key for **`root`** or another login user.

You still own the DigitalOcean account; the agent is just using **your** terminal session.

### Two different users often have cron jobs

On Ubuntu/DigitalOcean setups like yours, **pipelines** might live under a normal user (example: `mlsops`) while **database backups** sit under **`root`**. Check **both**:

```bash
ssh root@YOUR_DROPLET_IP 'crontab -l'
ssh mlsops@YOUR_DROPLET_IP 'crontab -l'
```

(Replace `YOUR_DROPLET_IP` with the IP shown in DigitalOcean → Droplets → your server.)

Or from an SSH session already logged in:

- `sudo crontab -u root -l`
- `sudo crontab -u mlsops -l`

### What “success” looks like

- **Pipeline jobs:** Lines containing `pipeline.py daily-active` and `pipeline.py weekly-sold-rented` (or `scripts/run_scheduled_pipeline.sh …`), pointing at your real project path (often `/opt/mls-automation`).
- **Backup job:** A line running `backup_postgres.sh` or similar, usually under `root`.

The repo’s template is `infra/cron.example`. **For production, `daily-active` must include `--with-scrape`** (often with `--headless`), or the job **never logs into MLS** and only re-processes **old CSV files** already on disk—a mistake that is invisible in Git because **cron lives only on the server.** Compare your live `crontab -l` to the template line by line at least once after any server setup or migration.

### If you prefer the browser

1. Log into **DigitalOcean** → **Droplets** → your server → **Access** → **Launch Droplet Console**.  
2. Run the same `crontab -l` / `sudo crontab -u mlsops -l` commands there.

**Why this isn’t only “in the repo”:** Cron lives on the server OS; Git cannot see it until someone runs these commands.

---

## B. Firewall so the database is not on the public internet

**Goal:** Outsiders can reach **SSH only** (port 22). Postgres stays **localhost-only** inside the server.

1. Same SSH/console session as above.
2. Follow the **Firewall (UFW)** commands in [hosted_scheduler_vm.md](hosted_scheduler_vm.md).
3. **Success:** `sudo ufw status verbose` shows **22/tcp ALLOW** and does **not** expose `5432` to the world.
4. Open a **second** SSH session before closing the first (so you don’t lock yourself out).

**Why you do this:** Firewall lives on the OS; the repo cannot toggle DigitalOcean firewalls for you.

---

## C. One real backup restore drill (prove backups work)

**Goal:** Prove you can recover from a bad upgrade or corrupted disk.

1. Ensure nightly dumps exist (see `scripts/backup_postgres.sh` on the server).
2. Pick **one** `.dump` file from `/opt/backups/mls/` (or your backup folder).
3. On a **maintenance window**, follow [postgres_restore_runbook.md](postgres_restore_runbook.md) exactly.
4. **Success:** After restore, `GET /health` returns OK and listing counts look sane.

**Why you do this:** Needs server access and acceptance of brief downtime risk.

---

## D. GitHub: require automated tests before merge (branch protection)

**Goal:** Pull requests cannot merge unless CI passes.

1. Open **github.com** → your repository → **Settings** → **Branches**.
2. **Add branch protection rule** for `main` (or `master`).
3. Enable **Require status checks to pass before merging**.
4. Select the **CI** workflow (from `.github/workflows/ci.yml`).
5. **Success:** A test PR shows a required check; merging is blocked until green.

**Why you do this:** Only a repo admin can change GitHub settings.

---

## E. “One week of reliability” (calendar item, not a button)

**Goal:** Confirm scheduled jobs succeed **most** days without you babysitting.

1. Do nothing special for **7 days** after cron is correct.
2. Open **`https://your-server…/ops`** (or SSH tunnel to `http://127.0.0.1:8000/ops` per README) **once per week**.
3. **Success:** Recent runs show green for `daily-active` and `weekly-sold-rented`, and counts don’t collapse unexpectedly.

**Why you do this:** Proof needs real time; code cannot fast-forward a calendar week.

---

## F. Rotating secrets (Slack webhook, MLS password)

**Goal:** Old secrets pasted in email/chat stop working.

1. In **Slack** / **MLS** websites, generate **new** credentials or webhooks per vendor docs.
2. On the server, edit **`/opt/mls-automation/.env`** (or your path)—never commit secrets to Git.
3. Restart anything that reads env at boot (systemd service or your `uvicorn` process) if applicable.

**Why you do this:** Vendors only show “reset password” to your logged-in browser session.

---

## G. Optional off-site backup copy (S3 / another region)

**Goal:** If the droplet vanishes, you still have database dumps elsewhere.

1. Pick a destination (DigitalOcean Spaces, AWS S3, etc.).
2. Create **bucket + API keys** in that product’s web UI.
3. Add a small **sync** cron on the server or use the provider’s “lifecycle copy” tools.

**Why you do this:** Cloud billing and bucket creation require your account.

---

If you tell me whether you use **DigitalOcean** only or also **GitHub**, I can narrow sections A/D to exact menu names on your next pass—but the sequence above is already sufficient for a developer or assistant to execute with you logged in for the browser-only steps.
