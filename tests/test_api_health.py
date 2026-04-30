import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client(monkeypatch):
    """In-memory SQLite so FastAPI tests run without Docker Postgres."""
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


def test_health_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_finance_mortgage_presets_shape(client: TestClient) -> None:
    r = client.get("/finance/mortgage-presets")
    assert r.status_code == 200
    body = r.json()
    assert body.get("schema_version") == 1
    presets = body.get("presets") or {}
    assert "30fixed" in presets
    assert "defaultAprPercent" in presets["30fixed"]
