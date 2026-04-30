from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Load repo-root `.env` so DATABASE_URL / MLS_* work without typing exports in the terminal.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_DEFAULT_LOCAL_DOCKER = "postgresql+psycopg://mls_user:mls_pass@localhost:5432/mls_analytics"


def _resolve_database_url() -> str:
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit
    # Production hosts should set DATABASE_URL in `.env` (or the environment). This guard catches
    # accidental deploys with no DB config while still allowing friction-free local Docker Compose.
    if os.getenv("MLS_PRODUCTION", "").strip() == "1":
        raise RuntimeError(
            "MLS_PRODUCTION=1 but DATABASE_URL is missing. Add DATABASE_URL to the server `.env` "
            "(same folder as this project), then restart the API / pipeline."
        )
    return _DEFAULT_LOCAL_DOCKER


DATABASE_URL = _resolve_database_url()

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
