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


def test_map_config_returns_keys_and_default_style(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAPBOX_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("MAPBOX_STYLE_URL", raising=False)
    r = client.get("/api/map-config")
    assert r.status_code == 200
    body = r.json()
    assert body["mapbox_access_token"] == ""
    assert body["map_style_url"].startswith("mapbox://")


def test_map_config_reads_env(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "pk.test-token")
    monkeypatch.setenv("MAPBOX_STYLE_URL", "mapbox://styles/mapbox/light-v11")
    r = client.get("/api/map-config")
    assert r.status_code == 200
    body = r.json()
    assert body["mapbox_access_token"] == "pk.test-token"
    assert body["map_style_url"] == "mapbox://styles/mapbox/light-v11"
