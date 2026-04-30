# Checklist execution report

This document records what was implemented locally in the repo against `docs/next_weeks_execution_checklist.md`. Items that require **your production VM**, **DNS/firewall**, or **vendor secrets** are marked **operator**.

## Completed in codebase

| Area | What changed |
|------|----------------|
| Phase 1 — freshness | `daily-active` loads Postgres by default; metrics include DB row counts for weekly/daily/load-db. |
| Phase 1 — visibility | Scheduler loads `.env`; optional HTTP Basic auth on `/ops*` when `OPS_BASIC_AUTH_USER/PASSWORD` set. |
| Phase 1 — rerun | `docs/rerun_playbook.md` documents replace semantics. |
| Phase 2 — secrets | Auto-load `.env`; default local Docker URL unless `MLS_PRODUCTION=1` (then `DATABASE_URL` required). |
| Phase 4 — single source | `sold_analytics_snapshot` table + `load_to_db` loader; `/sold-*` endpoints read DB snapshot (no CSV read/cache). |
| Phase 4 — DQ | Stronger `validate_monthly` checks on sold ZIP/price/bedrooms/settled dates. |
| Phase 5 — tests + CI | Pytest suite expanded; GitHub Actions workflow runs `pytest`. |
| Phase 5 — pins | `requirements.txt` pinned for reproducible installs. |
| Phase 6 — enrichment | `backend/enrichment/contracts.py` Protocols; static finance provider + `/finance/mortgage-presets`. |
| Phase 7 — adapters | `backend/listing_sources/active_listings.py` scraper vs VOW stub; `scripts/compare_listing_sources.py` ZIP harness. |
| Phase 3 — restore | `docs/postgres_restore_runbook.md` with `pg_restore` procedure. |

## Operator / environment (cannot be closed from repo alone)

- **Firewall / external port exposure**: validate on the VM (`ufw`, cloud SG).  
- **Off-site backup sync**: configure Spaces/S3/`rsync` target and credentials.  
- **One-week production reliability statistic**: needs calendar time on scheduled hosts.  
- **Secret rotation**: Slack webhook, MLS passwords — rotate per security checklist; update `.env` on servers only.

## Quick verification commands (developer)

```bash
python -m pip install -r requirements.txt
pytest tests -q
python pipeline.py validate-monthly   # needs data files
python pipeline.py load-db            # needs Postgres up + cleaned/analytics files
```

CI runs `pytest` without needing Docker Postgres (tests use an in-memory SQLite override).
