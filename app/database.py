from collections.abc import Mapping
import os
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from app.config import validate_environment

# Load variables from .env so the app works when run directly (uvicorn, no
# Docker). Inside Docker the env is already injected by docker-compose, and
# load_dotenv() is a harmless no-op there (it never overrides existing vars).
validate_environment()

DATABASE_URL = os.getenv("DATABASE_URL")


def _uses_transaction_pooler(database_url: str) -> bool:
    """Return whether the URL targets Supavisor transaction mode."""
    parsed = urlparse(database_url)
    return parsed.port == 6543


def _non_negative_int(
    environ: Mapping[str, str], name: str, default: int
) -> int:
    value = int(environ.get(name, str(default)).strip())
    if value < 0:
        raise ValueError(f"{name} must be zero or greater")
    return value


def database_engine_kwargs(
    database_url: str,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return bounded SQLAlchemy connection settings for the DB URL."""
    source = os.environ if environ is None else environ

    if database_url.startswith("sqlite"):
        return {}

    common: dict[str, object] = {
        "pool_pre_ping": True,
        "use_native_hstore": False,
        "connect_args": {
            "connect_timeout": _non_negative_int(
                source, "DB_CONNECT_TIMEOUT_SECONDS", 10
            )
        },
    }

    if _uses_transaction_pooler(database_url):
        # Supavisor owns the backend pool in transaction mode. Supabase
        # recommends NullPool for SQLAlchemy clients connected to port 6543.
        return {**common, "poolclass": NullPool}

    # Direct and session-mode connections are long lived. A small local pool
    # caps database sessions per worker and queues bursts instead of opening an
    # unbounded number of connections.
    return {
        **common,
        "poolclass": QueuePool,
        "pool_size": _non_negative_int(source, "DB_POOL_SIZE", 3),
        "max_overflow": _non_negative_int(source, "DB_MAX_OVERFLOW", 1),
        "pool_timeout": _non_negative_int(
            source, "DB_POOL_TIMEOUT_SECONDS", 10
        ),
        "pool_recycle": _non_negative_int(
            source, "DB_POOL_RECYCLE_SECONDS", 300
        ),
        "pool_use_lifo": True,
    }


engine = create_engine(DATABASE_URL, **database_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory():
    """Dependency returning the sessionmaker itself (not an open session).

    Slow endpoints (Supabase upload + Gemini can take 5-30s) use this to open
    short-lived sessions around their DB reads/writes instead of holding a
    pooled connection for the whole request. Tests override this dependency
    to point at the in-memory test engine.
    """
    return SessionLocal
