import os
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from supabase import create_client, Client

from app.database import get_db
from app import models

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

bearer_scheme = HTTPBearer()


@dataclass(frozen=True)
class SupabaseAuthContext:
    """Verified Supabase identity plus the JWT needed by downstream RLS."""

    supabase_uid: str
    access_token: str


@dataclass(frozen=True)
class AuthenticatedActor:
    role: Literal["owner", "vet"]
    user: models.User | None = None
    veterinarian: models.Veterinarian | None = None


def register_user(email: str, password: str):
    response = supabase.auth.sign_up({"email": email, "password": password})
    if not response.user:
        raise HTTPException(status_code=400, detail="Registration failed")
    return response


def login_user(email: str, password: str):
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not response.session:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return response


def request_password_reset(email: str, redirect_to: str | None = None):
    """Ask Supabase Auth to send its recovery email without exposing keys."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="Password reset is temporarily unavailable")
    try:
        options = {"redirect_to": redirect_to} if redirect_to else None
        return supabase.auth.reset_password_for_email(email, options)
    except Exception as exc:
        # Supabase can reject an otherwise syntactically valid address (for
        # example a reserved domain) or report that no matching user exists.
        # Treat those cases like a successful request so this endpoint cannot
        # be used to enumerate registered accounts.
        if getattr(exc, "code", None) in {
            "email_address_invalid",
            "user_not_found",
        }:
            return None
        raise HTTPException(status_code=503, detail="Password reset is temporarily unavailable")


def get_supabase_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> SupabaseAuthContext:
    """Validate the Bearer token and retain it for user-scoped integrations.

    The access token is never logged or returned to clients. Assessment uploads
    pass it to Supabase Storage so Storage RLS sees the same authenticated user
    that the API has already verified.
    """
    token = credentials.credentials

    try:
        response = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not response or not response.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return SupabaseAuthContext(
        supabase_uid=response.user.id,
        access_token=token,
    )


def get_supabase_uid(
    auth_context: SupabaseAuthContext = Depends(get_supabase_auth_context),
) -> str:
    """Return the verified uid without exposing the caller's access token."""

    return auth_context.supabase_uid


def get_current_user(
    supabase_uid: str = Depends(get_supabase_uid),
    db: Session = Depends(get_db),
) -> models.User:
    user = db.query(models.User).filter(models.User.supabase_uid == supabase_uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def get_current_veterinarian(
    supabase_uid: str = Depends(get_supabase_uid),
    db: Session = Depends(get_db),
) -> models.Veterinarian:
    vet = db.query(models.Veterinarian).filter(
        models.Veterinarian.supabase_uid == supabase_uid
    ).first()
    if not vet:
        raise HTTPException(status_code=401, detail="Veterinarian account not found")
    if vet.verification_status != "approved":
        raise HTTPException(status_code=403, detail="Veterinarian account is not approved")
    return vet


def get_current_actor(
    supabase_uid: str = Depends(get_supabase_uid),
    db: Session = Depends(get_db),
) -> AuthenticatedActor:
    user = db.query(models.User).filter(models.User.supabase_uid == supabase_uid).first()
    if user:
        return AuthenticatedActor(role="owner", user=user)
    vet = db.query(models.Veterinarian).filter(
        models.Veterinarian.supabase_uid == supabase_uid
    ).first()
    if not vet:
        raise HTTPException(status_code=401, detail="Account not found")
    if vet.verification_status != "approved":
        raise HTTPException(status_code=403, detail="Veterinarian account is not approved")
    return AuthenticatedActor(role="vet", veterinarian=vet)


def require_owned_pet(pet_id: int, current_user: models.User, db: Session) -> models.Pet:
    """Return the pet only if it exists AND belongs to the caller.

    Non-owned pets get the same 404 as missing ones so the API doesn't reveal
    which ids exist (URS-F2-09: no cross-account leakage).
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet or pet.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pet not found")
    return pet
