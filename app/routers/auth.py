import os
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app import models, schemas
from app.database import get_db
from app.auth import (
    register_user,
    login_user,
    request_password_reset,
    get_supabase_uid,
)

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)


class EmailCheckResponse(BaseModel):
    available: bool
    message: str


class PasswordResetRequest(BaseModel):
    email: str
    redirect_to: str | None = None


class PasswordResetResponse(BaseModel):
    message: str


def _actor_response(actor: models.User | models.Veterinarian) -> schemas.UserResponse:
    role = "veterinarian" if isinstance(actor, models.Veterinarian) else "owner"
    return schemas.UserResponse(
        id=actor.id,
        email=actor.email,
        name=actor.name,
        avatar_uri=actor.avatar_uri,
        role=role,
    )


def _validated_password_reset_redirect(requested: str | None) -> str | None:
    """Allow only configured recovery callbacks; never become an open redirect."""
    default = os.getenv("PASSWORD_RESET_REDIRECT_URL", "petto://reset-password").strip()
    candidate = (requested or default).strip()
    if not candidate:
        return None

    configured = {
        value.strip()
        for value in os.getenv("PASSWORD_RESET_REDIRECT_URLS", "").split(",")
        if value.strip()
    }
    if default:
        configured.add(default)
    if candidate in configured:
        return candidate

    parsed = urlparse(candidate)
    app_env = os.getenv("APP_ENV", "development").lower()
    is_local_web = (
        parsed.scheme in {"http", "https"}
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and app_env != "production"
    )
    if is_local_web:
        return candidate
    raise HTTPException(status_code=422, detail="Password reset redirect is not allowed")


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


@router.post("/forgot-password", response_model=PasswordResetResponse)
def forgot_password(req: PasswordResetRequest):
    """Send a recovery email while returning the same text for every address."""
    email = req.email.lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    redirect_to = _validated_password_reset_redirect(req.redirect_to)
    request_password_reset(email, redirect_to)
    return PasswordResetResponse(
        message="If an account exists for this email, a reset link has been sent."
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
        auth_session = response.session
        access_token = auth_session.access_token if auth_session else ""
    except HTTPException:
        raise
    except Exception:
        # The email already exists in Supabase Auth but has no public.users row
        # (e.g. a half-finished earlier signup). Recover by signing in instead of
        # 500-ing, so the account becomes usable.
        login_resp = login_user(email, req.password)
        supabase_uid = login_resp.user.id
        auth_session = login_resp.session
        access_token = auth_session.access_token

    # sign_up may not return a session (e.g. confirmation flow). Get one via
    # sign_in so the client always receives a usable token for the immediate
    # create-pet call that follows registration.
    if not access_token:
        login_resp = login_user(email, req.password)
        auth_session = login_resp.session
        access_token = auth_session.access_token

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
            db.add(models.PetWardrobeItem(
                pet_id=pet.id,
                accessory_id="acc_collar",
            ))
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
        refresh_token=getattr(auth_session, "refresh_token", None),
        expires_at=getattr(auth_session, "expires_at", None),
        user=_actor_response(user),
        pet=schemas.PetResponse.model_validate(created_pet) if created_pet else None,
    )


@router.post("/login", response_model=schemas.AuthResponse)
def login(req: schemas.LoginRequest, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    response = login_user(email, req.password)

    supabase_uid = response.user.id
    user = db.query(models.User).filter(models.User.supabase_uid == supabase_uid).first()

    if not user:
        veterinarian = db.query(models.Veterinarian).filter(
            models.Veterinarian.supabase_uid == supabase_uid
        ).first()
        if not veterinarian:
            veterinarian = db.query(models.Veterinarian).filter(
                models.Veterinarian.email == email
            ).first()
        if veterinarian:
            if veterinarian.verification_status != "approved":
                raise HTTPException(status_code=403, detail="Veterinarian account is not approved")
            if veterinarian.supabase_uid != supabase_uid:
                veterinarian.supabase_uid = supabase_uid
                db.commit()
                db.refresh(veterinarian)
            return schemas.AuthResponse(
                access_token=response.session.access_token,
                refresh_token=getattr(response.session, "refresh_token", None),
                expires_at=getattr(response.session, "expires_at", None),
                user=_actor_response(veterinarian),
            )

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
        refresh_token=getattr(response.session, "refresh_token", None),
        expires_at=getattr(response.session, "expires_at", None),
        user=_actor_response(user),
    )


@router.get("/me", response_model=schemas.UserResponse)
def get_me(
    supabase_uid: str = Depends(get_supabase_uid),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.supabase_uid == supabase_uid).first()
    if user:
        return _actor_response(user)
    veterinarian = db.query(models.Veterinarian).filter(
        models.Veterinarian.supabase_uid == supabase_uid
    ).first()
    if not veterinarian:
        raise HTTPException(status_code=401, detail="Account not found")
    if veterinarian.verification_status != "approved":
        raise HTTPException(status_code=403, detail="Veterinarian account is not approved")
    return _actor_response(veterinarian)
