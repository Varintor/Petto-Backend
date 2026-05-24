from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# ดึงค่า URL เชื่อมต่อฐานข้อมูลจาก docker-compose.yml
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