"""Smoke tests for expanded /ops JSON endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client(monkeypatch):
    from backend import db as db_module
    from backend.db import Base, get_db
    from backend.main import app

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite+pysqlite:///:memory:")
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def test_ops_overview_shape(client: TestClient) -> None:
    r = client.get("/ops/overview")
    assert r.status_code == 200
    j = r.json()
    assert j.get("api_ok") is True
    assert "active_listings_freshness" in j
    assert j["active_listings_freshness"].get("message")


def test_ops_disk_shape(client: TestClient) -> None:
    r = client.get("/ops/disk")
    assert r.status_code == 200
    j = r.json()
    assert "filesystem_used_pct" in j
    assert "heavy_dirs_bytes" in j


def test_ops_backup_status_shape(client: TestClient) -> None:
    r = client.get("/ops/backup-status")
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") in ("ok", "unknown")


def test_ops_schedule_status_shape(client: TestClient) -> None:
    r = client.get("/ops/schedule-status")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    if rows:
        assert "job_key" in rows[0]
        assert "schedule_hint" in rows[0]


def test_ops_runs_filters_ok(client: TestClient) -> None:
    r = client.get("/ops/runs?sort=failures_first&status=all&limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_ops_log_excerpt_missing_run(client: TestClient) -> None:
    r = client.get("/ops/runs/999999/log-excerpt")
    assert r.status_code == 404
