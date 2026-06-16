from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from app import models
from app.database import get_db

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
    notes: Optional[str] = None


class ConsultationResponse(BaseModel):
    id: int
    pet_id: int
    vet_id: int
    status: models.ConsultationStatus
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
@router.post("/consultations", response_model=ConsultationResponse)
def create_consultation(payload: ConsultationCreate, db: Session = Depends(get_db)):
    pet = db.query(models.Pet).filter(models.Pet.id == payload.pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")
    vet = db.query(models.Veterinarian).filter(models.Veterinarian.id == payload.vet_id).first()
    if not vet:
        raise HTTPException(status_code=404, detail="Veterinarian not found")

    db_consult = models.Consultation(**payload.model_dump())
    db.add(db_consult)
    db.commit()
    db.refresh(db_consult)
    return db_consult


@router.get("/pets/{pet_id}/consultations", response_model=List[ConsultationResponse])
def list_pet_consultations(pet_id: int, db: Session = Depends(get_db)):
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")
    return db.query(models.Consultation).filter(
        models.Consultation.pet_id == pet_id
    ).order_by(models.Consultation.created_at.desc()).all()


@router.get("/consultations/{consultation_id}", response_model=ConsultationResponse)
def get_consultation(consultation_id: int, db: Session = Depends(get_db)):
    consult = db.query(models.Consultation).filter(
        models.Consultation.id == consultation_id
    ).first()
    if not consult:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return consult


@router.put("/consultations/{consultation_id}/status", response_model=ConsultationResponse)
def update_status(consultation_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    consult = db.query(models.Consultation).filter(
        models.Consultation.id == consultation_id
    ).first()
    if not consult:
        raise HTTPException(status_code=404, detail="Consultation not found")

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
def send_message(consultation_id: int, payload: MessageCreate, db: Session = Depends(get_db)):
    consult = db.query(models.Consultation).filter(
        models.Consultation.id == consultation_id
    ).first()
    if not consult:
        raise HTTPException(status_code=404, detail="Consultation not found")

    if not payload.content and not payload.attachment_uri:
        raise HTTPException(status_code=400, detail="Message must have content or an attachment")

    try:
        sender = models.MessageSender(payload.sender_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="sender_type must be 'user' or 'vet'")

    db_msg = models.Message(
        consultation_id=consultation_id,
        sender_type=sender,
        sender_id=payload.sender_id,
        content=payload.content,
        attachment_uri=payload.attachment_uri,
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)
    return db_msg


@router.get("/consultations/{consultation_id}/messages", response_model=List[MessageResponse])
def list_messages(consultation_id: int, db: Session = Depends(get_db)):
    consult = db.query(models.Consultation).filter(
        models.Consultation.id == consultation_id
    ).first()
    if not consult:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return db.query(models.Message).filter(
        models.Message.consultation_id == consultation_id
    ).order_by(models.Message.created_at.asc()).all()
