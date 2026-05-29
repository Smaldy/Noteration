"""SQLite engine (WAL mode) and session factory.

WAL lets the background queue commit completed topics while the UI reads
concurrently — no writer-blocks-readers stalls. See docs/tech-stack.md.
"""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Local database file (gitignored). One file per install, single writer (queue).
DB_PATH = Path(__file__).resolve().parent.parent / "noteration.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    # FastAPI may touch the session from worker threads; SQLite needs this off.
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    """Enable WAL + foreign keys on every new connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Stable constraint names so Alembic (incl. SQLite batch ALTERs) generates
# deterministic, named constraints instead of anonymous ones.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_engine() -> Engine:
    """Expose the configured engine (used by Alembic env)."""
    return engine
