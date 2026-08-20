from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import os
from urllib.parse import urlparse

from app.config import validate_environment

# Load variables from .env so the app works when run directly (uvicorn, no
# Docker). Inside Docker the env is already injected by docker-compose, and
# load_dotenv() is a harmless no-op there (it never overrides existing vars).
validate_environment()

DATABASE_URL = os.getenv("DATABASE_URL")

def _uses_transaction_pooler(database_url: str) -> bool:
    parsed = urlparse(database_url)
    hostname = parsed.hostname or ""
    return parsed.port == 6543 or "pooler.supabase.com" in hostname


# SQLite (used by the test suite) keeps its default in-process pool. Supabase's
# transaction pooler already manages backend connections, so an extra SQLAlchemy
# QueuePool would just hold client connections open and can exhaust the pooler
# under load. Use NullPool there and only keep a local QueuePool for direct
# PostgreSQL connections.
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs = {}
elif _uses_transaction_pooler(DATABASE_URL):
    _engine_kwargs = {"poolclass": NullPool, "pool_pre_ping": True}
else:
    _engine_kwargs = {
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    }

engine = create_engine(DATABASE_URL, **_engine_kwargs)
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
