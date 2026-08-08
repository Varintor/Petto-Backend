from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app import models, schemas
from app.database import get_db
from app.auth import register_user, login_user, get_current_user

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)


class EmailCheckResponse(BaseModel):
    available: bool
    message: str


@router.get("/check-email", response_model=EmailCheckResponse)
def check_email_availability(email: str = Query(..., description="Email to check"), db: Session = Depends(get_db)):
    """Check if an email is already registered.

    Returns:
        - available: true if email can be used (not registered)
        - available: false if email already exists
    """
    # Normalize email for consistent checking
    email_lower = email.lower().strip()

    # Check in our database
    existing = db.query(models.User).filter(models.User.email == email_lower).first()
    if existing:
        return EmailCheckResponse(
            available=False,
            message="This email is already registered"
        )

    # Email is available (will also verify against Supabase on actual registration)
    return EmailCheckResponse(
        available=True,
        message="Email is available"
    )


@router.post("/register", response_model=schemas.AuthResponse)
def register(req: schemas.RegisterRequest, db: Session = Depends(get_db)):
    # Normalize like check-email does, so "Test@x.com" can't slip past the
    # duplicate check that "test@x.com" would have caught.
    email = req.email.lower().strip()

    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        response = register_user(email, req.password)
        supabase_uid = response.user.id
        access_token = response.session.access_token if response.session else ""
    except HTTPException:
        raise
    except Exception:
        # The email already exists in Supabase Auth but has no public.users row
        # (e.g. a half-finished earlier signup). Recover by signing in instead of
        # 500-ing, so the account becomes usable.
        login_resp = login_user(email, req.password)
        supabase_uid = login_resp.user.id
        access_token = login_resp.session.access_token

    # sign_up may not return a session (e.g. confirmation flow). Get one via
    # sign_in so the client always receives a usable token for the immediate
    # create-pet call that follows registration.
    if not access_token:
        login_resp = login_user(email, req.password)
        access_token = login_resp.session.access_token

    # Atomic write: user + pet land in the same DB transaction. If the pet
    # insert fails (validation, FK, constraint, whatever) we rollback the user
    # too, so the client never ends up "registered but no pet" — the exact
    # half-state that drove the empty-state bug on Home.
    created_pet: models.Pet | None = None
    try:
        user = models.User(
            supabase_uid=supabase_uid,
            email=email,
            name=req.name,
        )
        db.add(user)
        db.flush()  # assigns user.id without committing

        if req.pet is not None:
            pet = models.Pet(user_id=user.id, **req.pet.model_dump())
            db.add(pet)
            db.flush()  # surface any pet-side error inside the transaction
            created_pet = pet

        db.commit()
        db.refresh(user)
        if created_pet is not None:
            db.refresh(created_pet)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create account: {exc}",
        )

    return schemas.AuthResponse(
        access_token=access_token,
        user=schemas.UserResponse.model_validate(user),
        pet=schemas.PetResponse.model_validate(created_pet) if created_pet else None,
    )


@router.post("/login", response_model=schemas.AuthResponse)
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    response = login_user(email, req.password)

    supabase_uid = response.user.id
    user = db.query(models.User).filter(models.User.supabase_uid == supabase_uid).first()

    if not user:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user:
            user.supabase_uid = supabase_uid
            db.commit()
            db.refresh(user)
        else:
            # Auth user exists but has no profile row (e.g. created before the
            # backend bridge, or directly via Supabase). Self-heal by creating one
            # so the account can log in instead of 404-ing.
            user = models.User(
                supabase_uid=supabase_uid,
                email=email,
                name=(response.user.user_metadata or {}).get("name"),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    return schemas.AuthResponse(
        access_token=response.session.access_token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(get_current_user)):
    return schemas.UserResponse.model_validate(current_user)
