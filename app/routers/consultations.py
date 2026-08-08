import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from app import models
from app.auth import get_current_user, require_owned_pet
from app.database import get_db
from app.utils.time import now_bkk

router = APIRouter(
    prefix="/api/v1",
    tags=["Vet Consultation"],
)


# ==========================================
# Schemas
# ==========================================
class VetCreate(BaseModel):
    email: str
    name: str
    password_hash: str = "changeme"
    clinic_name: Optional[str] = None
    license_number: Optional[str] = None
    specialty: Optional[str] = None
    avatar_uri: Optional[str] = None
    is_online: bool = False


class VetResponse(BaseModel):
    id: int
    email: str
    name: str
    clinic_name: Optional[str] = None
    license_number: Optional[str] = None
    specialty: Optional[str] = None
    avatar_uri: Optional[str] = None
    is_online: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ConsultationCreate(BaseModel):
    pet_id: int
    vet_id: int
    # Optional AI assessment being forwarded for professional review (UD-06).
    assessment_id: Optional[int] = None
    notes: Optional[str] = None


class ConsultationResponse(BaseModel):
    id: int
    pet_id: int
    vet_id: int
    status: models.ConsultationStatus
    assessment_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StatusUpdate(BaseModel):
    status: str  # PENDING | ACTIVE | COMPLETED | CANCELLED


class MessageCreate(BaseModel):
    sender_type: str  # "user" | "vet"
    sender_id: Optional[int] = None
    content: Optional[str] = None
    attachment_uri: Optional[str] = None


class MessageResponse(BaseModel):
    id: int
    consultation_id: int
    sender_type: models.MessageSender
    sender_id: Optional[int] = None
    content: Optional[str] = None
    attachment_uri: Optional[str] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# Veterinarians
# ==========================================
@router.post("/veterinarians", response_model=VetResponse)
def create_vet(vet: VetCreate, db: Session = Depends(get_db)):
    # Dev/seed helper: real vet onboarding (Supabase-Auth vet accounts) is a
    # Progress II work item. Disabled on production unless explicitly enabled.
    if os.getenv("ENABLE_MOCK_DATA", "").lower() not in ("1", "true", "yes"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    db_vet = models.Veterinarian(**vet.model_dump())
    db.add(db_vet)
    db.commit()
    db.refresh(db_vet)
    return db_vet


@router.get("/veterinarians", response_model=List[VetResponse])
def list_vets(online_only: bool = False, db: Session = Depends(get_db)):
    query = db.query(models.Veterinarian)
    if online_only:
        query = query.filter(models.Veterinarian.is_online.is_(True))
    return query.order_by(models.Veterinarian.name.asc()).all()


# ==========================================
# Consultations
# ==========================================
def _require_owned_consultation(consultation_id: int, current_user: models.User, db: Session) -> models.Consultation:
    consult = db.query(models.Consultation).filter(
        models.Consultation.id == consultation_id
    ).first()
    if not consult:
        raise HTTPException(status_code=404, detail="Consultation not found")
    require_owned_pet(consult.pet_id, current_user, db)
    return consult


@router.post("/consultations", response_model=ConsultationResponse)
def create_consultation(
    payload: ConsultationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owned_pet(payload.pet_id, current_user, db)
    vet = db.query(models.Veterinarian).filter(models.Veterinarian.id == payload.vet_id).first()
    if not vet:
        raise HTTPException(status_code=404, detail="Veterinarian not found")
    if payload.assessment_id is not None:
        assessment = db.query(models.HealthAssessment).filter(
            models.HealthAssessment.id == payload.assessment_id,
            models.HealthAssessment.pet_id == payload.pet_id,
        ).first()
        if not assessment:
            raise HTTPException(status_code=404, detail="Assessment not found for this pet")

    db_consult = models.Consultation(**payload.model_dump())
    db.add(db_consult)
    db.commit()
    db.refresh(db_consult)
    return db_consult


@router.get("/pets/{pet_id}/consultations", response_model=List[ConsultationResponse])
def list_pet_consultations(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, current_user, db)
    return db.query(models.Consultation).filter(
        models.Consultation.pet_id == pet_id
    ).order_by(models.Consultation.created_at.desc()).all()


@router.get("/consultations/{consultation_id}", response_model=ConsultationResponse)
def get_consultation(
    consultation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _require_owned_consultation(consultation_id, current_user, db)


@router.put("/consultations/{consultation_id}/status", response_model=ConsultationResponse)
def update_status(
    consultation_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    consult = _require_owned_consultation(consultation_id, current_user, db)

    try:
        consult.status = models.ConsultationStatus[payload.status.upper()]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail="Status must be one of: PENDING, ACTIVE, COMPLETED, CANCELLED",
        )
    db.commit()
    db.refresh(consult)
    return consult


# ==========================================
# Messages
# ==========================================
@router.post("/consultations/{consultation_id}/messages", response_model=MessageResponse)
def send_message(
    consultation_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_owned_consultation(consultation_id, current_user, db)

    if not payload.content and not payload.attachment_uri:
        raise HTTPException(status_code=400, detail="Message must have content or an attachment")

    # Pet-owner tokens can only speak as "user". Vet-side messaging arrives
    # with vet Supabase-Auth accounts (Progress II); AI messages are created
    # server-side by the ai-summary endpoint.
    if payload.sender_type != "user":
        raise HTTPException(status_code=403, detail="Owners can only send as 'user'")

    db_msg = models.Message(
        consultation_id=consultation_id,
        sender_type=models.MessageSender.USER,
        sender_id=current_user.id,
        content=payload.content,
        attachment_uri=payload.attachment_uri,
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)
    return db_msg


@router.get("/consultations/{consultation_id}/messages", response_model=List[MessageResponse])
def list_messages(
    consultation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _require_owned_consultation(consultation_id, current_user, db)
    return db.query(models.Message).filter(
        models.Message.consultation_id == consultation_id
    ).order_by(models.Message.created_at.asc()).all()


# ==========================================
# AI Assistance (Feature 3)
# ==========================================
@router.post("/consultations/{consultation_id}/ai-summary", response_model=MessageResponse)
def post_ai_summary(
    consultation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Generate an AI-assist briefing for the vet and post it into the chat.

    Composes a structured summary of the pet profile, the forwarded/latest
    assessment, recent activity totals, and vaccination status, stored as a
    message with sender_type='ai'. Deterministic by design so it works without
    the Gemini key; polishing the wording through Gemini is a Progress II
    enhancement.
    """
    consult = _require_owned_consultation(consultation_id, current_user, db)
    pet = db.query(models.Pet).filter(models.Pet.id == consult.pet_id).first()

    assessment = None
    if consult.assessment_id:
        assessment = db.query(models.HealthAssessment).filter(
            models.HealthAssessment.id == consult.assessment_id
        ).first()
    if assessment is None:
        assessment = db.query(models.HealthAssessment).filter(
            models.HealthAssessment.pet_id == pet.id,
            models.HealthAssessment.status == "completed",
            models.HealthAssessment.risk_level.isnot(None),
        ).order_by(models.HealthAssessment.created_at.desc()).first()

    activities = db.query(models.ActivityLog).filter(
        models.ActivityLog.pet_id == pet.id
    ).order_by(models.ActivityLog.created_at.desc()).limit(30).all()
    total_min = sum(a.duration_minutes or 0 for a in activities)

    last_vac = db.query(models.Vaccination).filter(
        models.Vaccination.pet_id == pet.id
    ).order_by(models.Vaccination.date_administered.desc()).first()

    species_bit = ""
    if pet.species and pet.breed:
        species_bit = f" ({pet.species}, {pet.breed})"
    elif pet.species:
        species_bit = f" ({pet.species})"

    if assessment:
        risk = assessment.risk_level.value if assessment.risk_level else "n/a"
        snippet = (assessment.symptom_description or "")[:140]
        assessment_line = f"Latest AI check: {risk} - {snippet}"
    else:
        assessment_line = "No AI assessments recorded."

    if last_vac:
        vac_line = f"Last vaccination: {last_vac.vaccine_name} on {last_vac.date_administered}"
        if last_vac.next_due_date:
            vac_line += f", next due {last_vac.next_due_date}"
    else:
        vac_line = "No vaccination records."

    lines = [
        f"AI BRIEFING for {pet.name}{species_bit}",
        f"Weight: {pet.weight_kg} kg" if pet.weight_kg else None,
        assessment_line,
        f"Recent activity: {len(activities)} sessions, {total_min:.0f} min total.",
        vac_line,
        "Generated by Petto AI assist - preliminary information, not a diagnosis.",
    ]
    content = chr(10).join(x for x in lines if x)

    db_msg = models.Message(
        consultation_id=consultation_id,
        sender_type=models.MessageSender.AI,
        content=content,
    )
    db.add(db_msg)
    consult.updated_at = now_bkk()
    db.commit()
    db.refresh(db_msg)
    return db_msg
