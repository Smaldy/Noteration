"""Test fixtures: an isolated in-memory SQLite DB per test.

Mirrors the app's PRAGMAs (foreign_keys ON) so cascade/FK behavior is exercised
exactly as in production, without touching the real noteration.db.
"""

import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Keep the lifespan-started background worker out of the tests: API tests use
# `with TestClient(app)` (which runs lifespan), and the worker would otherwise
# spin up a thread against the real noteration.db. Tests drive the queue directly.
os.environ.setdefault("NOTERATION_DISABLE_WORKER", "1")

from backend.db.database import Base
import backend.models  # noqa: F401 - register all models on Base.metadata


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",  # in-memory
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
