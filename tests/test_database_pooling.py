import pytest
from sqlalchemy.pool import NullPool, QueuePool

from app.config import EnvironmentValidationError, validate_environment
from app.database import _uses_transaction_pooler, database_engine_kwargs


def _environment(database_url: str) -> dict[str, str]:
    return {
        "APP_ENV": "staging",
        "DATABASE_URL": database_url,
        "MIGRATION_DATABASE_URL": (
            "postgresql://postgres.project-ref:secret@"
            "aws-0-region.pooler.supabase.com:5432/postgres"
        ),
        "SUPABASE_URL": "https://project-ref.supabase.co",
        "SUPABASE_KEY": "test-publishable-key",
        "GEMINI_API_KEY": "test-gemini-key",
        "ENABLE_MOCK_DATA": "false",
    }


def test_only_port_6543_is_transaction_pooler_mode():
    assert _uses_transaction_pooler(
        "postgresql://postgres.ref:secret@aws.pooler.supabase.com:6543/postgres"
    )
    assert not _uses_transaction_pooler(
        "postgresql://postgres.ref:secret@aws.pooler.supabase.com:5432/postgres"
    )


def test_transaction_pooler_uses_supavisor_without_local_queue_pool():
    kwargs = database_engine_kwargs(
        "postgresql://postgres.ref:secret@aws.pooler.supabase.com:6543/postgres",
        {},
    )

    assert kwargs["poolclass"] is NullPool
    assert "pool_size" not in kwargs


def test_session_pooler_uses_small_bounded_queue_pool():
    kwargs = database_engine_kwargs(
        "postgresql://postgres.ref:secret@aws.pooler.supabase.com:5432/postgres",
        {
            "DB_POOL_SIZE": "4",
            "DB_MAX_OVERFLOW": "2",
            "DB_POOL_TIMEOUT_SECONDS": "7",
            "DB_POOL_RECYCLE_SECONDS": "240",
            "DB_CONNECT_TIMEOUT_SECONDS": "6",
        },
    )

    assert kwargs["poolclass"] is QueuePool
    assert kwargs["pool_size"] == 4
    assert kwargs["max_overflow"] == 2
    assert kwargs["pool_timeout"] == 7
    assert kwargs["pool_recycle"] == 240
    assert kwargs["connect_args"] == {"connect_timeout": 6}


def test_session_pooler_defaults_fit_small_managed_database():
    kwargs = database_engine_kwargs(
        "postgresql://postgres.ref:secret@aws.pooler.supabase.com:5432/postgres",
        {},
    )

    assert kwargs["poolclass"] is QueuePool
    assert kwargs["pool_size"] == 3
    assert kwargs["max_overflow"] == 1
    assert kwargs["pool_timeout"] == 10


def test_supabase_pooler_rejects_bare_postgres_username():
    values = _environment(
        "postgresql://postgres:secret@aws-0-region.pooler.supabase.com:5432/postgres"
    )

    with pytest.raises(
        EnvironmentValidationError,
        match="username must include the project reference",
    ):
        validate_environment(values)


def test_pool_limits_are_validated_before_startup():
    values = _environment(
        "postgresql://postgres.project-ref:secret@"
        "aws-0-region.pooler.supabase.com:5432/postgres"
    )
    values["DB_POOL_SIZE"] = "100"

    with pytest.raises(
        EnvironmentValidationError,
        match="DB_POOL_SIZE must be between 1 and 20",
    ):
        validate_environment(values)
