from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app.database import SessionLocal, get_db
from app import models

# Import ตัว Routers ต่างๆ ที่เราแยกไว้
from app.routers import vaccinations, assessments

# 1. ประกาศสร้างแอป FastAPI
app = FastAPI(title="Petto API", version="1.0.0")

# 2. เปิด CORS สำหรับ Flutter Web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # อนุญาตทุก origin (ใน production ควรระบุ URL เฉพาะ)
    allow_credentials=True,
    allow_methods=["*"],  # อนุญาตทุก HTTP method
    allow_headers=["*"],  # อนุญาตทุก header
)

# 2. นำ Routers มาเสียบเข้ากับตัวแอปหลัก (ต้องทำหลังประกาศ app นะครับ!)
app.include_router(vaccinations.router)
app.include_router(assessments.router)

@app.get("/", tags=["System"])
def read_root():
    return {"message": "Welcome to Petto Backend!"}

@app.get("/api/v1/setup-mock-data", tags=["System"])
def setup_mock_data(db: Session = Depends(get_db)):
    user = db.query(models.User).first()
    if not user:
        user = models.User(email="test@petto.com", name="Test Owner", password_hash="fake_hash")
        db.add(user)
        db.commit()
        db.refresh(user)

    pet = db.query(models.Pet).first()
    if not pet:
        pet = models.Pet(user_id=user.id, name="Buddy", species="Dog")
        db.add(pet)
        db.commit()
        db.refresh(pet)

    return {"message": "Mock data ready!", "pet_id": pet.id}