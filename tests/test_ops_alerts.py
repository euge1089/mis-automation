from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db import Base
from backend.models import PipelineRun
from backend.ops_alerts import daily_active_drop_status


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return testing_session()


def _add_daily_success(db: Session, finished_at: datetime, count: int | None) -> None:
    detail = {} if count is None else {"active_listings_after_cleaning": count}
    db.add(
        PipelineRun(
            job_key="daily-active",
            argv_json=["daily-active"],
            started_at=finished_at - timedelta(minutes=5),
            finished_at=finished_at,
            exit_code=0,
            hostname="test-host",
            git_sha="abc123",
            detail_json=detail,
        )
    )
    db.commit()


def test_daily_active_drop_status_insufficient_without_two_runs() -> None:
    db = _session()
    now = datetime.now(timezone.utc)
    _add_daily_success(db, now, 1000)

    status = daily_active_drop_status(db, threshold_pct=35.0)

    assert status["status"] == "insufficient_data"
    assert status["latest_count"] is None
    assert status["previous_count"] is None
    db.close()


def test_daily_active_drop_status_warns_on_large_drop() -> None:
    db = _session()
    now = datetime.now(timezone.utc)
    _add_daily_success(db, now - timedelta(days=1), 1000)
    _add_daily_success(db, now, 600)

    status = daily_active_drop_status(db, threshold_pct=35.0)

    assert status["status"] == "warn"
    assert status["latest_count"] == 600
    assert status["previous_count"] == 1000
    assert status["pct_change_vs_prior"] == -40.0
    db.close()


def test_daily_active_drop_status_ok_below_threshold() -> None:
    db = _session()
    now = datetime.now(timezone.utc)
    _add_daily_success(db, now - timedelta(days=1), 1000)
    _add_daily_success(db, now, 800)

    status = daily_active_drop_status(db, threshold_pct=35.0)

    assert status["status"] == "ok"
    assert status["latest_count"] == 800
    assert status["previous_count"] == 1000
    assert status["pct_change_vs_prior"] == -20.0
    db.close()
