"""Run Alembic migrations programmatically (used by the desktop launcher).

The packaged app has no terminal, so it can't run ``alembic upgrade head`` by
hand. This brings the per-user database up to ``head`` on every launch — a no-op
when already current, and the one-time schema creation on a fresh install.

``env.py`` resolves the engine/URL from ``backend.db.database`` (which reads
``backend.paths``), so this targets the correct SQLite file in dev, test, and
packaged builds alike. We only need to point Alembic at the migration scripts,
located relative to this module so it works inside a PyInstaller bundle too.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parent / "db" / "migrations"


def run_migrations() -> None:
    """Upgrade the database to the latest revision (creates it if missing)."""
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    command.upgrade(cfg, "head")


if __name__ == "__main__":  # `python -m backend.migrate` for manual use
    run_migrations()
    print(f"Migrations applied (scripts: {MIGRATIONS_DIR}).")
