from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

# Load variables from .env so the app works when run directly (uvicorn, no
# Docker). Inside Docker the env is already injected by docker-compose, and
# load_dotenv() is a harmless no-op there (it never overrides existing vars).
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is not set. "
        "Please set it in your deployment environment or docker-compose.yml"
    )

# pool_pre_ping recycles dead connections (important behind the Supabase
# Supavisor pooler / serverless), pool_recycle avoids stale long-lived ones.
# SQLite (used by the test suite) runs on SingletonThreadPool, which rejects
# the QueuePool sizing kwargs — only pass them for real server databases.
_engine_kwargs = {"pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,
    )

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