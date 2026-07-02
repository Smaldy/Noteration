"""Test fixtures: an isolated in-memory SQLite DB per test.

Mirrors the app's PRAGMAs (foreign_keys ON) so cascade/FK behavior is exercised
exactly as in production, without touching the real noteration.db. API tests
share the ``db_factory`` + ``client`` pair (StaticPool keeps the single
in-memory connection alive across the TestClient's threads); tests seed data
through ``db_factory`` and hit the app through ``client``.
"""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Keep the lifespan-started background worker out of the tests: API tests use
# `with TestClient(app)` (which runs lifespan), and the worker would otherwise
# spin up a thread against the real noteration.db. Tests drive the queue directly.
os.environ.setdefault("NOTERATION_DISABLE_WORKER", "1")
# TestClient sends `Host: testserver`; allow it through the local-origin guard.
os.environ.setdefault("NOTERATION_EXTRA_HOSTS", "testserver")

import backend.models  # noqa: F401 - register all models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app


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


@pytest.fixture
def db_factory() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared in-memory connection across threads
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(db_factory: sessionmaker) -> Generator[TestClient, None, None]:
    def _override() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
