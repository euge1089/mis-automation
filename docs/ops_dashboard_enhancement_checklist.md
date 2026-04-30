# Ops dashboard enhancement checklist (developer execution)

This document turns the **high / medium / lower** `/ops` roadmap into an executable plan with **verification gates**. **Excluded:** export-to-PDF (out of scope here).

**Audience:** Developers implementing features in this repo and deploying to the ops VM.

**Principles:**

- Every slice ships **API → UI → smoke test** before moving on.
- Prefer **additive** JSON fields and UI sections so older clients still work.
- Keep copy **plain-language** for non-technical operators; technical JSON stays behind disclosure.

---

## Prerequisites (once per epic)

- [ ] Read existing ops flow: `backend/ops_enrichment.py`, `backend/ops_logs.py`, `backend/main.py` (`/ops/*`), `frontend/ops.html`, `frontend/ops.js`, `frontend/ops.css`.
- [ ] Confirm `PipelineRun` model (`backend/models.py`) has `started_at`, `finished_at`, `exit_code`, `detail_json`, `argv_json`, `hostname`, `git_sha`.
- [ ] Local: `pytest tests`, `uvicorn` against Docker Postgres or SQLite test override per `tests/test_api_health.py`.
- [ ] Server: deploy path documented (`rsync` or `git pull`); `systemctl restart mls-api.service` after backend/static changes.

**Gate — prerequisites OK:** CI green locally; one manual `/health` + `/ops/runs` check passes.

---

# HIGH priority

## H1 — Plain-language “health at a glance” (overview strip)

**Goal:** One obvious strip at top of `/ops`: API up, last successful daily / weekly, data freshness hint.

### Tasks

- [ ] **Backend:** Add `GET /ops/overview` (or embed in existing bundle) returning structured fields, e.g.:
  - `api_ok: true` (always true if handler runs).
  - `last_success_daily_active: { finished_at, run_id } | null` — query `PipelineRun` for `job_key=daily-active`, `exit_code=0`, order by `finished_at` desc limit 1.
  - `last_success_weekly: …` same for `weekly-sold-rented`.
  - `last_success_load_db: …` optional if you rely on explicit `load-db` runs.
  - `active_listings_freshness: { source: "database"|"unknown", count: int|null, observed_at: iso }` — optional `SELECT COUNT(*)` + `MAX(updated_at)` if you add timestamps later; **v1** can use “last daily-active success time” as proxy for freshness.
- [ ] **Frontend:** New section above alerts: cards or one row with labels (“Last successful daily job”, “Last successful weekly job”, “You’re OK when…”).
- [ ] **Copy:** Short sentence what “fresh” means (e.g. “Daily job finished successfully” ≠ stale CSV).

### Verification

- [ ] `curl -s http://127.0.0.1:8000/ops/overview` returns JSON matching schema (add minimal Pydantic model in `schemas.py`).
- [ ] `/ops` renders strip without JS errors; refresh updates values.
- [ ] With **no** rows in DB, strip shows friendly “No runs yet” — no uncaught exceptions.

**Gate — H1 complete:** Overview matches DB after a known successful `pipeline.py` run.

---

## H2 — Per-run log excerpt (time-aligned slice)

**Goal:** For each run card, show **log lines falling between `started_at` and `finished_at`** (best-effort from rolling file), not only full-file tail.

### Tasks

- [ ] **Backend:** Extend `backend/ops_logs.py`:
  - Parse rolling log lines; filter by timestamp if logs prefix ISO timestamps; **if not**, filter lines between **byte offsets** approximated by scanning for run banner strings (e.g. `=== DAILY ACTIVE PIPELINE START ===`) inserted by `pipeline.py` — **minimum viable:** store run **start marker** in `detail_json` at end of run (e.g. `log_marker`) — **prefer** adding one `print` with unique id in `pipeline.py` finish — **or** heuristic: return last **N** lines before `finished_at` from same job log by scanning file once with bounded read.
  - New endpoint: `GET /ops/runs/{id}/log-excerpt?max_lines=200` returning `{ content, resolved_path, note }` where `note` explains approximation.
- [ ] **Frontend:** Per run: “View log for **this** run” opens modal calling **run-scoped** excerpt; keep existing “rolling log” for full file.
- [ ] **Security:** Same auth as `/ops/*`; no path parameters beyond run id.

### Verification

- [ ] Run pipeline twice; second run shows excerpt **not** identical to entire file when file is large.
- [ ] Failed run still returns excerpt or clear `note` if empty.

**Gate — H2 complete:** Manual comparison: excerpt timestamps overlap `[started_at, finished_at]` on sample log.

---

## H3 — Failures first + readable error summary

**Goal:** Toggle or default sort: failures on top; surface `detail_json.error` as human line without expanding JSON.

### Tasks

- [ ] **Backend:** `GET /ops/runs` supports `?status=failed|success|all` (default `all`) and `?sort=recent|failures_first`.
  - Failed = `exit_code IS NOT NULL AND exit_code != 0`.
- [ ] **Frontend:** Toggle “Show failures first”; badge “Error” with one-line `detail_json.error` truncated (200 chars) + expand.
- [ ] **Ops enrichment:** Add `error_summary` field on `OpsRunRowOut` from `detail_json.get("error")`.

### Verification

- [ ] Seed or simulate failed run (`exit_code=1`); appears first when `failures_first`.
- [ ] Success-only filter hides failures.

**Gate — H3 complete:** Non-technical user can spot “what broke” without opening technical JSON.

---

## H4 — Disk pressure (project data volume)

**Goal:** Show **used space / free space** for filesystem holding `/opt/mls-automation` (or `PROJECT_DIR`), and optional size of `downloads/` + `history/`.

### Tasks

- [ ] **Backend:** `GET /ops/disk` (ops-auth) using `shutil.disk_usage(PROJECT_DIR)` and optional `du`-style sums via `os.walk` with **caps** (max seconds, skip if too large) **or** subprocess `du -sb` on fixed allowlisted paths only (`downloads`, `history`, `logs`).
- [ ] **Frontend:** Small card in overview: “Disk: X% used (~Y GB free)” + link “Heavy folders” breakdown.
- [ ] **Safety:** Never expose paths outside project root; timeout on walk.

### Verification

- [ ] Works on macOS dev and Linux server.
- [ ] Large dirs don’t block request > 2s (use sampling or `du` with timeout).

**Gate — H4 complete:** Values update on refresh; plausible vs `df -h` on server.

---

### HIGH — Integration gate (before calling HIGH “done”)

- [ ] All new endpoints documented in README API section.
- [ ] `pytest` extended with mocked disk / mocked log read where practical.
- [ ] Deploy to staging or ops VM; smoke test `/ops` as non-root user with Basic auth if enabled.

---

# MEDIUM priority

## M1 — Scrape-oriented headline metrics

**Goal:** When `argv` indicates scrape, show **duration** (`finished_at - started_at`), **export file count** from `detail_json`, first stderr line if failure.

### Tasks

- [ ] **Backend:** Ensure `gather_run_metrics` / `finish_pipeline_run` includes `duration_seconds` and `with_scrape` already implied by argv; add `scrape_export_files` if distinct from combined metrics.
- [ ] **Frontend:** Extra line in metric_lines area for scrape runs.

### Verification

- [ ] One run with `--with-scrape` shows duration; one without does not claim scrape.

**Gate — M1 complete.**

---

## M2 — Schedule hint vs last run (expectations)

**Goal:** Show **expected next window** (document-driven cron summary) vs **last actual** finish — **v1 static** table from `ops_catalog` schedule hints + dynamic last success from DB.

### Tasks

- [ ] **Frontend:** Table: Job | “Typically runs” (from `JOB_HELP.schedule_hint`) | “Last finished (ET)”.
- [ ] Optional **backend:** `cron_explanation.md` single source if hints drift.

### Verification

- [ ] Times display America/New_York consistently with rest of ops page.

**Gate — M2 complete.**

---

## M3 — Backup visibility

**Goal:** Surface last backup without SSH: e.g. **heartbeat file** written by `backup_postgres.sh` (`/opt/backups/mls/.last_backup.json` with timestamp + size) **or** parse latest file mtime in backup dir (read-only, allowlisted).

### Tasks

- [ ] **Script:** Extend `scripts/backup_postgres.sh` to write heartbeat next to dump.
- [ ] **Backend:** `GET /ops/backup-status` reads heartbeat or newest `*.dump` mtime under allowlisted `BACKUP_ROOT` env default.
- [ ] **Frontend:** Card “Last database backup: …”.

### Verification

- [ ] After manual backup run, heartbeat updates.

**Gate — M3 complete.**

---

### MEDIUM — Integration gate

- [ ] Cross-browser smoke (Safari/Chrome) on `/ops`.
- [ ] Load test: `/ops/overview` + `/ops/disk` under 500ms on server.

---

# LOWER priority

## L1 — “Deep” metrics scope boundary

**Goal:** Avoid bloating `/ops` with full Prometheus-style charts; **either** link out **or** one small “CPU load” widget later.

### Tasks

- [ ] Document decision in this file: **defer** CPU/memory graphs unless product asks.
- [ ] Optional: `GET /ops/host-load` returning 1m loadavg from `/proc/loadavg` (Linux only) behind flag `OPS_EXTENDED_METRICS=1`.

### Verification

- [ ] If disabled, no extra dependencies or privileged calls.

**Gate — L1:** Explicit product sign-off before expanding.

---

## L2 — Operator onboarding tooltip tour (optional)

**Goal:** First-visit tooltips or collapsible “How to read this page”.

### Tasks

- [ ] Copy-only section in `ops.html` + minimal CSS.

**Gate — L2:** Non-technical reviewer approves wording.

---

### LOWER — Integration gate

- [ ] No regression on `/` main app.

---

## Final release checklist (all tiers shipped)

- [ ] README API list updated for every new route.
- [ ] `docs/non_technical_operator_steps.md` references new dashboard capabilities (one paragraph).
- [ ] Deploy: rsync or git; `pip install -r requirements.txt`; `systemctl restart mls-api.service`.
- [ ] Post-deploy: `/health`, `/ops`, `/ops/overview`, `/ops/disk` (if implemented), one failed-run scenario tested on staging.

---

## Suggested build order (minimize rework)

1. **H1** overview API + UI (unblocks everything else visually).
2. **H3** failures filter + error summary (high user value, low coupling).
3. **H4** disk (isolated endpoint).
4. **H2** log excerpt (most intricate — log format assumptions).
5. **M1 → M2 → M3** in order.
6. **L1 / L2** as time permits.

Track progress by copying this file into a PR description or ticking boxes in the implementing PR.
