import os
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


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    token = credentials.credentials

    try:
        response = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if not response or not response.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    supabase_uid = response.user.id
    user = db.query(models.User).filter(models.User.supabase_uid == supabase_uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
