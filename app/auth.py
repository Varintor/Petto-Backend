import os
from dataclasses import dataclass

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


def require_owned_pet(pet_id: int, current_user: models.User, db: Session) -> models.Pet:
    """Return the pet only if it exists AND belongs to the caller.

    Non-owned pets get the same 404 as missing ones so the API doesn't reveal
    which ids exist (URS-F2-09: no cross-account leakage).
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet or pet.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pet not found")
    return pet
