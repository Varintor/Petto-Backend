"""Railway pre-deploy entry point: validate, migrate, and verify the DB."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.config import validate_environment


logger = logging.getLogger("petto.predeploy")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run() -> None:
    app_env = validate_environment(require_migration_url=True)
    migration_url = os.getenv("MIGRATION_DATABASE_URL") or os.environ["DATABASE_URL"]

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", migration_url)
    expected = tuple(sorted(ScriptDirectory.from_config(config).get_heads()))

    logger.warning("Running database migrations for APP_ENV=%s", app_env)
    command.upgrade(config, "head")

    migration_engine = create_engine(migration_url, poolclass=NullPool, pool_pre_ping=True)
    try:
        with migration_engine.connect() as connection:
            current = tuple(
                sorted(MigrationContext.configure(connection).get_current_heads())
            )
    finally:
        migration_engine.dispose()

    if current != expected:
        raise RuntimeError(
            f"Migration verification failed: current={current}, expected={expected}"
        )

    logger.warning("Database migration verified at %s", ",".join(current))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
