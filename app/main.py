import os
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import SessionLocal, get_db
from app import models
from app.readiness import check_readiness

from app.routers import (
    auth, vaccinations, assessments, pets, activities, stats, missions, consultations,
    history, devices,
)

app = FastAPI(title="Petto API", version="1.0.0")

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


@app.exception_handler(Exception)
async def cors_safe_exception_handler(request: Request, exc: Exception):
    # Log the real error server-side; clients get a generic message so we
    # don't leak internals (SQL, file paths, upstream API errors).
    import logging
    logging.getLogger("petto").exception("Unhandled error on %s %s", request.method, request.url.path)
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
        },
    )

app.include_router(auth.router)
app.include_router(vaccinations.router)
app.include_router(assessments.router)
app.include_router(pets.router)
app.include_router(activities.router)
app.include_router(missions.router)
app.include_router(consultations.router)
app.include_router(stats.router)
app.include_router(history.router)
app.include_router(devices.router)

@app.get("/", tags=["System"])
def read_root():
    return {"message": "Welcome to Petto Backend!"}

@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "service": "petto-backend",
        "version": "1.0.0"
    }


@app.get("/ready", tags=["System"])
def readiness_check():
    result = check_readiness()
    payload = {"status": "ready" if result.ready else "not_ready", **result.to_dict()}
    return JSONResponse(status_code=200 if result.ready else 503, content=payload)

@app.get("/api/v1/setup-mock-data", tags=["System"])
def setup_mock_data(db: Session = Depends(get_db)):
    # Dev-only seeding helper. Disabled unless explicitly enabled, so the
    # public production API can't be used to write mock rows.
    if os.getenv("ENABLE_MOCK_DATA", "").lower() not in ("1", "true", "yes"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

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
