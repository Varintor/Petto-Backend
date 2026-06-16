from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.auth import register_user, login_user, get_current_user

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)


@router.post("/register", response_model=schemas.AuthResponse)
def register(req: schemas.RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    response = register_user(req.email, req.password)

    user = models.User(
        supabase_uid=response.user.id,
        email=req.email,
        name=req.name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = response.session.access_token if response.session else ""

    return schemas.AuthResponse(
        access_token=access_token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.post("/login", response_model=schemas.AuthResponse)
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    response = login_user(req.email, req.password)

    supabase_uid = response.user.id
    user = db.query(models.User).filter(models.User.supabase_uid == supabase_uid).first()

    if not user:
        user = db.query(models.User).filter(models.User.email == req.email).first()
        if user:
            user.supabase_uid = supabase_uid
            db.commit()
            db.refresh(user)
        else:
            raise HTTPException(status_code=404, detail="User record not found")

    return schemas.AuthResponse(
        access_token=response.session.access_token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return schemas.UserResponse.model_validate(current_user)
