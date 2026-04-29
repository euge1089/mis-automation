# Next actions: security, dashboard, backups

Prioritized checklist for production readiness. Order within each section is **recommended sequence** unless noted.

---

## 1. Security

| Priority | Action | Why |
|:--------:|--------|-----|
| P0 | **Rotate Slack inbound webhook** if it was ever pasted in chat/email; update `/opt/mls-automation/.env` on the VM; restart anything that reads it at startup if applicable | Secrets in plain text elsewhere are high risk |
| P0 | **Confirm GitHub repo is Private** | Source + architecture docs should not be public for a brokerage stack |
| P0 | **Firewall (`ufw`) on the VM**: allow **22/tcp** (SSH); **deny** inbound **5432** (Postgres should stay localhost-only—already bound to `127.0.0.1` in `docker-compose.yml`) | Reduces attack surface |
| P1 | **Decide API exposure**: keep **`uvicorn` only on localhost** and use **SSH tunnel** from your Mac to hit `:8000`, *or* put **Caddy/nginx + HTTPS** + optional **Tailscale**/VPN in front | No credential-free API on the public internet |
| P1 | **SSH hardening**: disable password auth if not needed (`PasswordAuthentication no`), confirm key-only login for `root` / `mlsops` | Prevents brute force |
| P1 | **Non-root Docker usage** (optional): run containers as unprivileged user where images allow | Defense in depth |
| P2 | **Automated security updates** on Ubuntu (`unattended-upgrades` for security patches) | Keeps kernel/libs patched |
| P2 | **Secrets management** long-term: move env vars to a **single** root-readable file or host secret store; never commit `.env` | Already gitignored—enforce on new machines |

**Definition of done (security baseline):** Private repo, rotated webhooks, `ufw` with SSH allowed and DB not exposed, API not world-readable without TLS + auth decision documented.

---

## 2. Dashboard (run health & checks)

Goal: **one place** to see whether scheduled jobs succeeded, when they last ran, and whether data looks sane—without tailing raw logs daily.

| Priority | Action | Why |
|:--------:|--------|-----|
| P0 | **Persist run records**: each pipeline invocation appends a JSON line (or row) with `command`, `started_at`, `finished_at`, `exit_code`, `host`, optional `git_sha` | Foundation for UI + alerting |
| P0 | **Structured log summary**: capture last N lines of stderr on failure or store high-level counts (rows combined, memorialized counts) in that record | Explains failures without SSH |
| P1 | **API endpoints** (read-only): e.g. `GET /ops/runs?limit=50`, `GET /ops/summary` (last success per job type) | Frontend + scripts consume same data |
| P1 | **Minimal web UI** (static or React): table of runs (green/red), timestamps in **America/New_York**, link to open **Slack** if webhook configured | Matches your “check dashboard instead of Slack” workflow |
| P2 | **Threshold alerts** (already partly specified): relaxed active drop %, sold/rented min rows—surface in UI + optional Slack | Same rules as discussed; document in UI tooltips |
| P2 | **Auth**: if dashboard is ever reachable beyond localhost, add **Tailscale**, **basic auth**, or **OAuth**—not needed if only SSH tunnel | Avoid public anonymous ops data |

**Definition of done (dashboard v1):** After a cron run, you can open a page and see success/failure and last run time without SSH.

---

## 3. Backups

| Priority | Action | Why |
|:--------:|--------|-----|
| P0 | **Postgres logical dumps**: nightly `pg_dump` (custom format `-Fc`) of `mls_analytics` to a file outside the container, e.g. `/opt/backups/mls/` with dated filenames | Recover from corruption or bad migration |
| P0 | **Retention policy**: keep e.g. **7 daily** + **4 weekly** + **12 monthly** (adjust to taste); prune old files with a small script | Disk control |
| P1 | **Off-droplet copy**: sync dumps to **S3-compatible storage**, **another region**, or **encrypted USB/cloud** you control | Droplet loss ≠ data loss |
| P1 | **Test restore** once: restore dump to a **temporary** local DB and verify table counts | Proves backups work |
| P2 | **Application config backup**: tarball of `/opt/mls-automation/.env` (encrypted or restricted), `cron`, `systemd` unit, `docker-compose` | Faster rebuild of ops layer |
| P2 | **Checkpoint JSON** under `history/checkpoints/`—include in tar if not already covered by DB dump | Resume state for long backfills |

**Definition of done (backups baseline):** Automated nightly DB dump, retention, one successful restore test documented in a short runbook note.

---

## Suggested order across workstreams

1. **Security P0** (firewall + repo private + webhook rotate)—same day.  
2. **Backups P0** (automated `pg_dump` + retention)—before you rely on VM as sole copy of history.  
3. **Dashboard P0–P1** (run persistence + API + minimal UI)—improves daily confidence.  
4. **Security P1** (API exposure decision + SSH tuning).  
5. **Backups P1** (off-site sync).  
6. Remaining P2 items as time allows.

---

## Open decisions (you choose)

- **Dashboard auth**: localhost/tunnel only vs password vs Tailscale.  
- **Backup destination**: DigitalOcean Spaces vs AWS S3 vs another cloud vs periodic manual download.  
- **Compliance**: whether MLS requires retaining raw CSV extracts—if yes, add archive-before-delete policy (separate from current “clear before scrape” behavior).
