"""Database and migration readiness checks used by Railway health probes."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine


logger = logging.getLogger("petto.readiness")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    database: str
    migration: str
    current_revisions: tuple[str, ...] = ()
    expected_revisions: tuple[str, ...] = ()
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@lru_cache(maxsize=1)
def expected_database_revisions() -> tuple[str, ...]:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    return tuple(sorted(script.get_heads()))


def check_readiness() -> ReadinessResult:
    expected = expected_database_revisions()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            current = tuple(
                sorted(
                    row[0]
                    for row in connection.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                )
            )
    except SQLAlchemyError:
        logger.exception("Readiness database check failed")
        return ReadinessResult(
            ready=False,
            database="unavailable",
            migration="unknown",
            expected_revisions=expected,
            reason="database_unavailable",
        )

    if current != expected:
        return ReadinessResult(
            ready=False,
            database="available",
            migration="out_of_date",
            current_revisions=current,
            expected_revisions=expected,
            reason="migration_mismatch",
        )

    return ReadinessResult(
        ready=True,
        database="available",
        migration="current",
        current_revisions=current,
        expected_revisions=expected,
    )
