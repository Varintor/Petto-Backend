"""Public pet card: opaque bearer URL with an allow-listed response."""
import hashlib
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, require_owned_pet
from app.database import get_db
from app.utils.time import now_bkk

router = APIRouter(prefix="/api/v1", tags=["Public Pet Card"])
ALLOWED = {"name", "photo", "species", "breed", "allergies", "chronic_conditions", "current_medications", "emergency_notes", "contact_method"}
_reads: dict[str, list[datetime]] = {}


class CardWrite(BaseModel):
    is_active: bool = True
    visible_fields: list[str] = Field(default_factory=list, max_length=9)
    contact_method: Optional[str] = Field(default=None, max_length=255)
    emergency_notes: Optional[str] = Field(default=None, max_length=2000)


def _hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()
def _token() -> str: return secrets.token_urlsafe(32)


def _owned(pet_id, user, db):
    require_owned_pet(pet_id, user, db)
    return db.query(models.PublicPetCard).filter_by(pet_id=pet_id).first()


def _view(card, token=None):
    return {"id": card.id, "pet_id": card.pet_id, "is_active": card.is_active, "visible_fields": card.visible_fields or [], "contact_method": card.contact_method, "emergency_notes": card.emergency_notes, "revoked_at": card.revoked_at, **({"token": token} if token else {})}


@router.put("/pets/{pet_id}/public-card")
def upsert(pet_id: int, body: CardWrite, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    invalid = set(body.visible_fields) - ALLOWED
    if invalid: raise HTTPException(422, f"Unsupported visible fields: {sorted(invalid)}")
    card = _owned(pet_id, user, db); token = None
    if not card:
        token = _token(); card = models.PublicPetCard(pet_id=pet_id, token_hash=_hash(token)); db.add(card)
    for key, value in body.model_dump().items(): setattr(card, key, value)
    card.updated_at = now_bkk(); card.revoked_at = None if body.is_active else card.revoked_at
    db.commit(); db.refresh(card); return _view(card, token)


@router.get("/pets/{pet_id}/public-card")
def settings(pet_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    card = _owned(pet_id, user, db)
    if not card: raise HTTPException(404, "Public card not configured")
    return _view(card)


@router.post("/pets/{pet_id}/public-card/rotate")
def rotate(pet_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    card = _owned(pet_id, user, db)
    if not card: raise HTTPException(404, "Public card not configured")
    token = _token(); card.token_hash = _hash(token); card.is_active = True; card.revoked_at = None; card.updated_at = now_bkk(); db.commit(); return _view(card, token)


@router.post("/pets/{pet_id}/public-card/revoke")
def revoke(pet_id: int, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    card = _owned(pet_id, user, db)
    if not card: raise HTTPException(404, "Public card not configured")
    card.is_active = False; card.revoked_at = now_bkk(); db.commit(); return _view(card)


@router.get("/public/pets/{token}")
def public_read(token: str, request: Request, db: Session = Depends(get_db)):
    key = request.client.host if request.client else "unknown"; now = now_bkk()
    recent = [t for t in _reads.get(key, []) if (now - t).total_seconds() < 60]
    if len(recent) >= 60: raise HTTPException(429, "Too many requests")
    recent.append(now); _reads[key] = recent
    card = db.query(models.PublicPetCard).filter_by(token_hash=_hash(token), is_active=True, revoked_at=None).first()
    if not card: raise HTTPException(404, "Public card is invalid, expired, or revoked")
    pet, profile, visible = card.pet, card.pet.health_profile, set(card.visible_fields or [])
    values = {"name": pet.name, "photo": pet.avatar_uri, "species": pet.species, "breed": pet.breed, "allergies": profile.allergies if profile else [], "chronic_conditions": profile.chronic_conditions if profile else [], "current_medications": profile.current_medications if profile else [], "emergency_notes": card.emergency_notes, "contact_method": card.contact_method}
    return {k: values[k] for k in visible}
