"""Public pet card: opaque bearer URL with an allow-listed response."""
import hashlib
import secrets
from html import escape
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
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


def _find_public_card(token: str, request: Request, db: Session):
    key = request.client.host if request.client else "unknown"; now = now_bkk()
    recent = [t for t in _reads.get(key, []) if (now - t).total_seconds() < 60]
    if len(recent) >= 60: raise HTTPException(429, "Too many requests")
    recent.append(now); _reads[key] = recent
    card = db.query(models.PublicPetCard).filter_by(token_hash=_hash(token), is_active=True, revoked_at=None).first()
    if not card: raise HTTPException(404, "Public card is invalid, expired, or revoked")
    return card


def _public_values(card) -> dict:
    pet, profile, visible = card.pet, card.pet.health_profile, set(card.visible_fields or [])
    values = {
        "name": pet.name,
        "photo": pet.avatar_uri,
        "species": pet.species,
        "breed": pet.breed,
        "allergies": profile.allergies if profile else [],
        "chronic_conditions": profile.chronic_conditions if profile else [],
        "current_medications": profile.current_medications if profile else [],
        "emergency_notes": card.emergency_notes,
        "contact_method": card.contact_method,
    }
    return {key: values[key] for key in ALLOWED if key in visible}


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
    return _public_values(_find_public_card(token, request, db))


def _list(value) -> str:
    if not value:
        return '<span class="muted">Not provided</span>'
    return "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in value) + "</ul>"


@router.get("/public/pets/{token}/card", response_class=HTMLResponse)
def public_card_page(token: str, request: Request, db: Session = Depends(get_db)):
    """Human-readable, allow-listed card for QR codes and NFC tags."""
    values = _public_values(_find_public_card(token, request, db))
    name = escape(str(values.get("name") or "Pet Health Card"))
    identity = " · ".join(
        escape(str(values[key]))
        for key in ("species", "breed")
        if values.get(key)
    )
    rows = []
    labels = {
        "allergies": "Allergies",
        "chronic_conditions": "Chronic conditions",
        "current_medications": "Current medications",
        "emergency_notes": "Emergency notes",
        "contact_method": "Owner contact",
    }
    for key, label in labels.items():
        if key not in values:
            continue
        raw = values[key]
        content = _list(raw) if isinstance(raw, list) else escape(str(raw or "Not provided"))
        rows.append(f'<section><h2>{label}</h2><div>{content}</div></section>')
    body = "".join(rows) or '<p class="muted">The owner has not shared additional health details.</p>'
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive"><title>{name} · Petto Health Card</title>
<style>
body{{margin:0;background:#fff7f2;color:#482a2a;font:16px system-ui,-apple-system,sans-serif}}
main{{max-width:680px;margin:0 auto;padding:28px 18px 48px}}header{{background:#8f3136;color:white;padding:28px;border-radius:24px;box-shadow:0 12px 30px #8f313626}}
.brand{{font-size:13px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;opacity:.86}}h1{{font-size:34px;margin:8px 0 4px}}header p{{margin:0;opacity:.9}}
section{{background:white;border:1px solid #edd9d4;border-radius:18px;margin-top:14px;padding:18px 20px}}h2{{font-size:14px;text-transform:uppercase;letter-spacing:.08em;color:#8f3136;margin:0 0 8px}}ul{{margin:0;padding-left:20px}}.muted{{color:#826f6f}}footer{{font-size:12px;color:#8a7676;text-align:center;margin-top:24px}}
</style></head><body><main><header><div class="brand">Petto · Pet Health Card</div><h1>{name}</h1><p>{identity}</p></header>{body}<footer>Emergency summary shared by the pet owner. Verify medical decisions with a veterinarian.</footer></main></body></html>"""
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "X-Content-Type-Options": "nosniff",
        },
    )
