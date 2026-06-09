import os
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import SessionLocal, get_db
from app import models

# Import ตัว Routers ต่างๆ ที่เราแยกไว้
from app.routers import (
    vaccinations, assessments, pets, activities, stats, missions, consultations,
)

# 1. ประกาศสร้างแอป FastAPI
app = FastAPI(title="Petto API", version="1.0.0")

# 2. เปิด CORS สำหรับ Flutter Web / Mobile
#
# Production-safe rule: a wildcard origin ("*") and allow_credentials=True
# cannot be combined — browsers reject it and Starlette refuses to echo "*"
# with credentials. We have no cookie/credential auth yet, so credentials are
# off and "*" works for both Flutter mobile (CORS doesn't apply) and web.
# When real auth (cookies) lands, set ALLOWED_ORIGINS to explicit domains and
# flip allow_credentials back on.
_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Ensure unhandled 500 errors still carry CORS headers. Without this, a server
# crash returns a response with no Access-Control-Allow-Origin, so browsers
# (Flutter Web) block it and the client only sees an opaque "connection error"
# instead of the real error. We attach the headers manually here.
@app.exception_handler(Exception)
async def cors_safe_exception_handler(request: Request, exc: Exception):
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {type(exc).__name__}: {exc}"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        },
    )

# 2. นำ Routers มาเสียบเข้ากับตัวแอปหลัก (ต้องทำหลังประกาศ app นะครับ!)
app.include_router(vaccinations.router)
app.include_router(assessments.router)
app.include_router(pets.router)
app.include_router(activities.router)
app.include_router(missions.router)
app.include_router(consultations.router)
app.include_router(stats.router)

@app.get("/", tags=["System"])
def read_root():
    return {"message": "Welcome to Petto Backend!"}

@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint สำหรับ Railway"""
    return {
        "status": "healthy",
        "service": "petto-backend",
        "version": "1.0.0"
    }

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