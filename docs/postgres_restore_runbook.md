# Postgres restore runbook

Use this after you have at least one custom-format dump from `scripts/backup_postgres.sh` (files named like `mls_YYYYMMDD-HHMMSSZ.dump`).

## Preconditions

- Docker container running (`mls-postgis` by default).
- You know `PGPASSWORD` for user `mls_user` (matches `docker-compose.yml` / VM `.env`).

## Inspect a dump (safe)

```bash
docker exec -e PGPASSWORD="$PGPASSWORD" mls-postgis pg_restore -l /path/in/container.dump | head
```

Copy the dump into the container first if needed:

```bash
docker cp /opt/backups/mls/mls_20260429-120000Z.dump mls-postgis:/tmp/restore.dump
docker exec -e PGPASSWORD="$PGPASSWORD" mls-postgis pg_restore -l /tmp/restore.dump | head
```

## Restore into the existing database (destructive)

**Warning:** this replaces objects in `mls_analytics`. Run during maintenance.

```bash
docker exec -e PGPASSWORD="$PGPASSWORD" mls-postgis \
  pg_restore -U mls_user -d mls_analytics --clean --if-exists --no-owner --role=mls_user \
  /tmp/restore.dump
```

## Verify

```bash
docker exec -e PGPASSWORD="$PGPASSWORD" mls-postgis \
  psql -U mls_user -d mls_analytics -c "SELECT COUNT(*) FROM active_listings;"
```

Then hit `GET /health` and a few read endpoints locally (`127.0.0.1`).

## Definition of done

- Restore completes without fatal errors (warnings may appear for extensions).
- Row counts are plausible versus last known baseline.
- API serves `/health` and listing/analytics routes against the restored DB.
