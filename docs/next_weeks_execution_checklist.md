# MLS Automation: Next-Weeks Execution Checklist

**Execution status:** Automated work completed in-repo is summarized in [checklist_execution_report.md](checklist_execution_report.md). Steps that require your hosted VM, firewall, vendor portals, or calendar time remain **operator-run**.

Use this as the working runbook for the next 4-6 weeks. The goal is to harden what exists, remove fragile behavior, and prepare for enrichment + VOW migration without a rewrite.

How to use this checklist:
- Work top to bottom.
- Do not start the next phase until all phase exit checks pass.
- If a check fails, stop and fix before moving on.
- Keep notes in each phase under "Implementation Notes" with date + owner.

---

## Phase 0: Preflight and baseline lock (Day 1)

### 0.1 Snapshot current state
- [ ] Pull latest branch and confirm clean working tree (or document local WIP).
- [ ] Capture current scheduler behavior and API status.
- [ ] Save baseline metrics:
  - [ ] Last 7 `daily-active` run statuses.
  - [ ] Last 4 `weekly-sold-rented` run statuses.
  - [ ] Current row counts: `active_listings`, `sold_listing_history`, `rented_listing_history`.
  - [ ] Current API latency sample for `/health`, `/active-listings?limit=10`, `/ops/summary`.

### 0.2 Baseline checks
- [ ] Run tests:
  - [ ] `pytest tests` (or project equivalent).
  - [ ] Confirm zero failing tests.
- [ ] Run local smoke:
  - [ ] `python pipeline.py validate-monthly`
  - [ ] `python pipeline.py validate-daily-active`
  - [ ] `uvicorn backend.main:app --host 127.0.0.1 --port 8000`
  - [ ] Confirm `/health` returns `{"status":"ok"}`.

### 0.3 Exit criteria
- [ ] All baseline commands complete without exceptions.
- [ ] Baseline metrics recorded in project notes.
- [ ] Any known failures are logged as explicit backlog items.

Implementation Notes:
- Date:
- Owner:
- Notes:

---

## Phase 1: Reliability hardening (Week 1)

### 1.1 Daily freshness guarantee
- [x] Ensure `daily-active` loads to DB by default.
- [x] Cron template + scheduler script documented (`infra/cron.example`, `scripts/run_scheduled_pipeline.sh` loads `.env`).
- [ ] Confirm production VM crontab matches repo template **(operator)**.
- [ ] Remove any redundant cron job that only exists to compensate for stale daily loads **(operator)**.

Validation checks:
- [ ] Trigger one manual run: `python pipeline.py daily-active --with-scrape --headless`.
- [ ] Confirm run record exists in `/ops/runs`.
- [ ] Confirm `active_listings` row count changes after run.
- [ ] Confirm `/active-listings?limit=5` reflects newly loaded data.

### 1.2 Pipeline failure visibility
- [x] Replace silent `except ...: pass` in scraper flows with explicit warning/error logging **(started in `main.py`; extend to `active_main.py` / `rentals_main.py` as needed)**.
- [x] Run-level counters in `detail_json` via `backend/run_metrics.py` (CSV row counts + DB row counts for sold snapshot / active).
- [x] Failed pipeline exits non-zero via `pipeline.py` exception propagation + run record.

Validation checks:
- [ ] Simulate one controlled scraper failure (bad input file or invalid path).
- [ ] Confirm run marked failed in `/ops/runs`.
- [ ] Confirm failure message is readable and actionable.
- [ ] Confirm no silent success state after a failed step.

### 1.3 Idempotency and rerun confidence
- [ ] Verify rerunning `daily-active` twice in a row does not create duplicate active records **(operator / staging)**.
- [ ] Verify rerunning `weekly-sold-rented` memorialization does not duplicate historical windows **(operator / staging)**.
- [x] Document rerun procedure in [rerun_playbook.md](rerun_playbook.md).

Validation checks:
- [ ] Run same command twice.
- [ ] Compare row counts and key uniqueness constraints.
- [ ] Confirm expected replace/merge behavior by table.

### 1.4 Exit criteria
- [ ] One full week of daily runs with zero stale DB incidents.
- [ ] No silent exception patterns in scraper core paths.
- [ ] Rerun behavior validated and documented.

Implementation Notes:
- Date:
- Owner:
- Notes:

---

## Phase 2: Security and access controls (Week 1-2)

### 2.1 Network exposure controls
- [ ] Confirm API binds to localhost unless intentionally proxied.
- [ ] Confirm Postgres remains localhost-only.
- [ ] Confirm VM firewall allows SSH only (or explicitly approved additional ports).

Validation checks:
- [ ] From another host, verify API port is not publicly reachable (unless intended).
- [ ] `ss -lntp` / equivalent confirms expected bind addresses.
- [ ] External port scan shows only approved ports.

### 2.2 Secrets hygiene
- [x] Auto-load `.env`; safe local default URL; `MLS_PRODUCTION=1` requires explicit `DATABASE_URL` (see `backend/db.py`).
- [x] Document env-driven configuration in README.
- [ ] Rotate any secret previously exposed in chat/email/plain text **(operator)**.

Validation checks:
- [ ] Start app with only env-provided secrets.
- [ ] Confirm app fails fast with clear message when required secrets missing.
- [ ] Confirm no secrets in git-tracked files (`.env` remains ignored).

### 2.3 Ops UI/API protection decision
- [x] Optional HTTP Basic auth for `/ops*` when `OPS_BASIC_AUTH_USER` / `OPS_BASIC_AUTH_PASSWORD` are set (`backend/main.py`).
- [ ] Choose production exposure: localhost/tunnel vs TLS proxy **(operator)**.

Validation checks:
- [ ] Unauthorized network access attempt is denied.
- [ ] Authorized access path tested end-to-end.

### 2.4 Exit criteria
- [ ] Security baseline defined, implemented, and documented.
- [ ] Secrets rotation completed and logged.
- [ ] Exposure model tested from outside host.

Implementation Notes:
- Date:
- Owner:
- Notes:

---

## Phase 3: Backup and restore reliability (Week 2)

### 3.1 Automated backups
- [ ] Schedule nightly `pg_dump` to persistent disk.
- [ ] Add retention policy script (daily/weekly/monthly windows).
- [ ] Add off-host copy (S3/Spaces/other encrypted remote target).

Validation checks:
- [ ] Backup file appears nightly with expected size.
- [ ] Retention cleanup keeps intended count.
- [ ] Off-host sync job succeeds and is auditable.

### 3.2 Restore test (non-optional)
- [x] Restore procedure documented in [postgres_restore_runbook.md](postgres_restore_runbook.md).
- [ ] Execute one real restore drill on staging **(operator)**.

Validation checks:
- [ ] Restored DB row counts are within expected tolerance.
- [ ] API can point to restored DB and serve core endpoints.
- [ ] Restore runbook updated with lessons learned.

### 3.3 Exit criteria
- [ ] Nightly backups run automatically.
- [ ] At least one successful restore test documented.
- [ ] Recovery process can be executed by a new developer.

Implementation Notes:
- Date:
- Owner:
- Notes:

---

## Phase 4: Single source of truth and data model cleanup (Week 2-3)

### 4.1 Remove split source behavior
- [x] Sold analytics use `sold_analytics_snapshot` loaded by `load_to_db` (see [analytics_refresh.md](analytics_refresh.md)).
- [x] Refresh strategy documented.

Validation checks:
- [ ] Delete/rename local sold CSV and confirm API still serves sold analytics from DB.
- [ ] Compare old vs new endpoint results on same filter set (within acceptable tolerance).
- [ ] Confirm API restart is no longer required to pick up sold updates.

### 4.2 Data quality gate improvements
- [x] Expanded `validate_monthly_outputs` checks for sold ZIPs, prices, bedrooms, settled-date parse rate (`data_quality.py`).

Validation checks:
- [ ] Inject known-bad sample rows in test data.
- [ ] Confirm validation catches and fails with precise error message.

### 4.3 Exit criteria
- [ ] Core analytics endpoints rely on DB-backed truth.
- [ ] Data quality checks catch synthetic bad inputs.
- [ ] No cache-induced stale sold analytics behavior.

Implementation Notes:
- Date:
- Owner:
- Notes:

---

## Phase 5: Test coverage and CI safety net (Week 3)

### 5.1 Expand automated tests
- [x] API smoke tests (`tests/test_api_health.py`) + finance/listing/enrichment unit tests.
- [ ] Full pipeline integration tests **(optional stretch)**.

Validation checks:
- [ ] Tests run locally in under agreed threshold (example: < 5 minutes).
- [ ] New tests fail when intentionally breaking a key transform.

### 5.2 CI setup
- [x] GitHub Actions workflow `.github/workflows/ci.yml` runs `pytest`.
- [ ] Branch protection / required checks **(operator, GitHub settings)**.

Validation checks:
- [ ] Open test PR with intentional failing test; confirm CI blocks.
- [ ] Fix and confirm CI returns green.

### 5.3 Dependency reproducibility
- [x] Pinned versions in `requirements.txt`.

Validation checks:
- [ ] Fresh environment install reproducibly succeeds.
- [ ] CI uses same dependency strategy as local development.

### 5.4 Exit criteria
- [ ] CI is enforced on contribution path.
- [ ] Regression coverage exists for highest-risk flows.
- [ ] New developer can clone and run tests without guesswork.

Implementation Notes:
- Date:
- Owner:
- Notes:

---

## Phase 6: Enrichment-ready architecture (Week 3-4)

### 6.1 Create enrichment module contracts
- [x] Protocols + metadata dataclass in `backend/enrichment/contracts.py`.

Validation checks:
- [ ] Contract tests pass for required fields and null-handling.
- [ ] Joining enrichment onto active listings does not explode row counts.

### 6.2 Finance provider abstraction
- [x] `StaticFinanceRateProvider` + `GET /finance/mortgage-presets` (`backend/finance_provider.py`).
- [ ] Optional: hydrate dashboard from API instead of embedded constants **(frontend follow-up)**.

Validation checks:
- [ ] API returns same shape regardless of provider implementation.
- [ ] Switching provider via config does not require frontend rewrite.

### 6.3 Exit criteria
- [ ] Enrichment modules can be added without changing scraper internals.
- [ ] Provider abstraction is swap-ready and test-covered.

Implementation Notes:
- Date:
- Owner:
- Notes:

---

## Phase 7: VOW migration readiness without cutover (Week 4-6)

### 7.1 Active source adapter boundary
- [x] `backend/listing_sources/active_listings.py` (`ScraperActiveListingSource`, `VowFeedActiveListingSource` stub).

Validation checks:
- [ ] Existing scraper path still works through adapter boundary.
- [ ] Adapter tests validate required canonical fields.

### 7.2 Dual-source comparison harness
- [x] `scripts/compare_listing_sources.py` (ZIP bucket comparison JSON report).

Validation checks:
- [ ] Harness runs against fixture data now.
- [ ] Report format is deterministic and easy to review.

### 7.3 Exit criteria
- [ ] System is ready for low-risk VOW swap when feed access is granted.
- [ ] No downstream API redesign required for source change.

Implementation Notes:
- Date:
- Owner:
- Notes:

---

## Ongoing weekly operating checklist (run every week)

### Weekly health checks
- [ ] Review `/ops/summary` and verify expected run cadence.
- [ ] Review last 7 run failures and identify recurring root causes.
- [ ] Confirm latest backup exists and off-host sync succeeded.
- [ ] Check data quality trends (row counts, drop thresholds, validation warnings).
- [ ] Confirm no abnormal API error spikes.

### Weekly maintenance checks
- [ ] Review dependency/security advisories.
- [ ] Confirm disk usage for `downloads/`, `history/`, and backup paths.
- [ ] Confirm cron/system timers are present after any host update/reboot.
- [ ] Confirm SSL/auth posture remains as intended.

### Weekly reporting artifacts
- [ ] Publish one-page status:
  - [ ] reliability score (runs succeeded / scheduled)
  - [ ] data freshness status
  - [ ] backup restore confidence
  - [ ] top 3 risks and owners

---

## Definition of "production-safe beta"

All items below must be true:
- [ ] Daily and weekly pipelines succeed at target reliability (example: >= 95%).
- [ ] Data freshness for active listings verified daily.
- [ ] Backups + restore tested and documented.
- [ ] No unauthenticated public exposure of API/ops.
- [ ] CI catches common regressions before merge.
- [ ] Source adapter boundary exists for VOW migration.

