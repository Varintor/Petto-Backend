from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# ดึงค่า URL เชื่อมต่อฐานข้อมูลจาก docker-compose.yml
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()