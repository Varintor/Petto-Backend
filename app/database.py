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
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()