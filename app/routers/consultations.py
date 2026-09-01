import math
import os
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.auth import (
    AuthenticatedActor,
    SupabaseAuthContext,
    get_current_actor,
    get_current_user,
    get_supabase_auth_context,
    require_owned_pet,
)
from app.database import get_db
from app.storage import create_assessment_signed_url
from app.utils.time import now_bkk

router = APIRouter(prefix="/api/v1", tags=["Vet Consultation"])


class VetCreate(BaseModel):
    email: str
    name: str
    password_hash: str = "changeme"
    clinic_name: str | None = None
    license_number: str | None = None
    specialty: str | None = None
    avatar_uri: str | None = None
    is_online: bool = False


class VetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    clinic_name: str | None
    license_number: str | None
    specialty: str | None
    avatar_uri: str | None
    is_online: bool
    verification_status: str
    is_accepting_consultations: bool
    created_at: datetime


class ProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    provider_type: str
    address: str | None
    phone: str | None
    latitude: float | None
    longitude: float | None
    operating_hours: dict | None
    provider_status: str
    consultation_enabled: bool
    distance_km: float | None = None


class ConsultationCreate(BaseModel):
    pet_id: int
    vet_id: int
    provider_id: int | None = None
    assessment_id: int | None = None
    subject: str | None = Field(default=None, max_length=200)
    notes: str | None = None
    priority: Literal["normal", "urgent"] = "normal"
    urgent_help_acknowledged: bool = False


class ConsultationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pet_id: int
    vet_id: int
    provider_id: int | None
    status: models.ConsultationStatus
    priority: str
    assessment_id: int | None
    subject: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime | None
    closed_at: datetime | None
    pet_name: str | None = None
    pet_species: str | None = None
    owner_name: str | None = None
    vet_name: str | None = None
    provider_name: str | None = None


class StatusUpdate(BaseModel):
    status: Literal["PENDING", "ACTIVE", "COMPLETED", "CANCELLED"]


class MessageCreate(BaseModel):
    content: str | None = None
    attachment_uri: str | None = None
    client_message_id: uuid.UUID | None = None
    # Retained only for compatibility. Identity is always derived from JWT.
    sender_type: Literal["user", "vet"] | None = None
    sender_id: int | None = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    consultation_id: int
    sender_type: models.MessageSender
    sender_id: int | None
    content: str | None
    attachment_uri: str | None
    message_type: str
    client_message_id: uuid.UUID | None
    is_read: bool
    delivered_at: datetime | None
    read_at: datetime | None
    created_at: datetime


class ShareAssessmentRequest(BaseModel):
    assessment_id: int


class SharedAssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    consultation_id: int
    assessment_id: int
    shared_at: datetime
    revoked_at: datetime | None


class SharedAssessmentDetailResponse(SharedAssessmentResponse):
    assessment: schemas.AssessmentResponse


class AppointmentCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime | None = None
    reason: str | None = None


class AppointmentDecision(BaseModel):
    decision: Literal["accepted", "declined"]


class AppointmentUpdate(BaseModel):
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reason: str | None = None


class AppointmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    consultation_id: int
    pet_id: int
    provider_id: int | None
    proposed_by_vet_id: int
    starts_at: datetime
    ends_at: datetime | None
    reason: str | None
    status: str
    responded_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _sync_appointment_calendar(
    appointment: models.Appointment, db: Session
) -> None:
    """Keep the accepted appointment and its Calendar projection atomic."""
    event = db.query(models.CalendarEvent).filter_by(
        appointment_id=appointment.id
    ).first()
    if appointment.status != "accepted":
        if event is not None:
            db.delete(event)
        return
    if event is None:
        event = models.CalendarEvent(
            pet_id=appointment.pet_id,
            appointment_id=appointment.id,
            title="Veterinary appointment",
            event_type="vet",
            reminder_minutes=30,
        )
        db.add(event)
    event.event_date = appointment.starts_at.date()
    event.starts_at = appointment.starts_at
    event.updated_at = now_bkk()


def _consultation_query(db: Session):
    """Load display data with the consultation and avoid per-row queries."""
    return db.query(models.Consultation).options(
        joinedload(models.Consultation.pet).joinedload(models.Pet.owner),
        joinedload(models.Consultation.vet),
        joinedload(models.Consultation.provider),
    )


def _consultation_response(
    consultation: models.Consultation,
) -> ConsultationResponse:
    pet = consultation.pet
    return ConsultationResponse.model_validate(consultation).model_copy(
        update={
            "pet_name": pet.name if pet else None,
            "pet_species": pet.species if pet else None,
            "owner_name": pet.owner.name if pet and pet.owner else None,
            "vet_name": consultation.vet.name if consultation.vet else None,
            "provider_name": (
                consultation.provider.name if consultation.provider else None
            ),
        }
    )


def _require_participant(
    consultation_id: int, actor: AuthenticatedActor, db: Session
) -> models.Consultation:
    consultation = _consultation_query(db).filter_by(id=consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    if actor.role == "owner":
        # The participant query already eager-loads the pet. Reusing it avoids
        # one extra round trip on every chat/messages/appointment request.
        pet = consultation.pet
        allowed = bool(pet and pet.user_id == actor.user.id)
    else:
        allowed = consultation.vet_id == actor.veterinarian.id
    if not allowed:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return consultation


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    value = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


@router.post("/veterinarians", response_model=VetResponse)
def create_vet(vet: VetCreate, db: Session = Depends(get_db)):
    if os.getenv("ENABLE_MOCK_DATA", "").lower() not in ("1", "true", "yes"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    db_vet = models.Veterinarian(**vet.model_dump(), verification_status="approved")
    db.add(db_vet)
    db.commit()
    db.refresh(db_vet)
    return db_vet


@router.get("/veterinarians", response_model=list[VetResponse])
def list_vets(
    online_only: bool = False,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    query = db.query(models.Veterinarian).filter(
        models.Veterinarian.verification_status == "approved"
    )
    if online_only:
        query = query.filter(models.Veterinarian.is_online.is_(True))
    return query.order_by(models.Veterinarian.name).all()


@router.get("/veterinary-providers", response_model=list[ProviderResponse])
def list_providers(
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    consultation_only: bool = False,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    query = db.query(models.VeterinaryProvider).filter(
        models.VeterinaryProvider.provider_status != "disabled"
    )
    if consultation_only:
        query = query.filter(models.VeterinaryProvider.consultation_enabled.is_(True))
    providers = query.limit(limit).all()
    result = []
    for provider in providers:
        item = ProviderResponse.model_validate(provider)
        if latitude is not None and longitude is not None and provider.latitude is not None and provider.longitude is not None:
            item.distance_km = round(_haversine_km(latitude, longitude, float(provider.latitude), float(provider.longitude)), 2)
        result.append(item)
    if latitude is not None and longitude is not None:
        result.sort(key=lambda p: p.distance_km if p.distance_km is not None else float("inf"))
    return result


@router.get(
    "/veterinary-providers/{provider_id}/veterinarians",
    response_model=list[VetResponse],
)
def list_provider_veterinarians(
    provider_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """List verified veterinarians available through one Petto provider."""
    provider = db.query(models.VeterinaryProvider).filter_by(id=provider_id).first()
    if not provider or provider.provider_status == "disabled":
        raise HTTPException(status_code=404, detail="Veterinary provider not found")
    if not provider.consultation_enabled:
        return []
    return (
        db.query(models.Veterinarian)
        .join(models.ProviderVeterinarian)
        .filter(
            models.ProviderVeterinarian.provider_id == provider_id,
            models.ProviderVeterinarian.is_active.is_(True),
            models.ProviderVeterinarian.accepting_consultations.is_(True),
            models.Veterinarian.verification_status == "approved",
            models.Veterinarian.is_accepting_consultations.is_(True),
        )
        .order_by(models.Veterinarian.name)
        .all()
    )


@router.post("/consultations", response_model=ConsultationResponse)
def create_consultation(
    payload: ConsultationCreate,
    db: Session = Depends(get_db),
    owner: models.User = Depends(get_current_user),
):
    require_owned_pet(payload.pet_id, owner, db)
    if payload.priority == "urgent":
        if not payload.urgent_help_acknowledged:
            raise HTTPException(
                status_code=422,
                detail="Urgent Help disclaimer must be acknowledged",
            )
        if payload.provider_id is None:
            raise HTTPException(
                status_code=422,
                detail="Urgent Help requires a Petto-enabled provider",
            )
    vet = db.query(models.Veterinarian).filter_by(id=payload.vet_id).first()
    if not vet or vet.verification_status != "approved":
        raise HTTPException(status_code=404, detail="Verified veterinarian not found")
    if not vet.is_accepting_consultations:
        raise HTTPException(status_code=409, detail="Veterinarian is not accepting consultations")
    if payload.provider_id is not None:
        link = db.query(models.ProviderVeterinarian).join(models.VeterinaryProvider).filter(
            models.ProviderVeterinarian.provider_id == payload.provider_id,
            models.ProviderVeterinarian.veterinarian_id == payload.vet_id,
            models.ProviderVeterinarian.is_active.is_(True),
            models.ProviderVeterinarian.accepting_consultations.is_(True),
            models.VeterinaryProvider.consultation_enabled.is_(True),
        ).first()
        if not link:
            raise HTTPException(status_code=409, detail="Consultation is not available for this provider")
    assessment = None
    if payload.assessment_id is not None:
        assessment = db.query(models.HealthAssessment).filter_by(
            id=payload.assessment_id, pet_id=payload.pet_id
        ).first()
        if not assessment:
            raise HTTPException(status_code=404, detail="Assessment not found for this pet")
    consultation_data = payload.model_dump(exclude={"urgent_help_acknowledged"})
    if payload.priority == "urgent" and not payload.subject:
        consultation_data["subject"] = "Urgent Help"
    consultation = models.Consultation(**consultation_data)
    db.add(consultation)
    db.flush()
    if assessment:
        db.add(models.ConsultationSharedAssessment(
            consultation_id=consultation.id,
            assessment_id=assessment.id,
            shared_by_user_id=owner.id,
        ))
    db.commit()
    db.refresh(consultation)
    return _consultation_response(consultation)


@router.get("/pets/{pet_id}/consultations", response_model=list[ConsultationResponse])
def list_pet_consultations(
    pet_id: int,
    db: Session = Depends(get_db),
    owner: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, owner, db)
    consultations = _consultation_query(db).filter_by(pet_id=pet_id).order_by(
        models.Consultation.updated_at.desc()
    ).all()
    return [_consultation_response(item) for item in consultations]


@router.get("/vet/consultations", response_model=list[ConsultationResponse])
def list_vet_consultations(
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    if actor.role != "vet":
        raise HTTPException(status_code=403, detail="Veterinarian access required")
    consultations = (
        _consultation_query(db)
        .filter_by(vet_id=actor.veterinarian.id)
        .order_by(models.Consultation.updated_at.desc())
        .all()
    )
    return [_consultation_response(item) for item in consultations]


@router.get("/consultations/{consultation_id}", response_model=ConsultationResponse)
def get_consultation(
    consultation_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    consultation = _require_participant(consultation_id, actor, db)
    return _consultation_response(consultation)


@router.put("/consultations/{consultation_id}/status", response_model=ConsultationResponse)
def update_status(
    consultation_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    consultation = _require_participant(consultation_id, actor, db)
    consultation.status = models.ConsultationStatus[payload.status]
    consultation.updated_at = now_bkk()
    consultation.closed_at = now_bkk() if payload.status in {"COMPLETED", "CANCELLED"} else None
    db.commit()
    db.refresh(consultation)
    return _consultation_response(consultation)


@router.post("/consultations/{consultation_id}/messages", response_model=MessageResponse)
def send_message(
    consultation_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    consultation = _require_participant(consultation_id, actor, db)
    if consultation.status in {
        models.ConsultationStatus.COMPLETED,
        models.ConsultationStatus.CANCELLED,
    }:
        raise HTTPException(
            status_code=409,
            detail="Messages cannot be sent to a closed consultation",
        )
    if not payload.content and not payload.attachment_uri:
        raise HTTPException(status_code=400, detail="Message must have content or an attachment")
    actual_sender = "user" if actor.role == "owner" else "vet"
    if payload.sender_type and payload.sender_type != actual_sender:
        raise HTTPException(status_code=403, detail="Message sender must match authenticated account")
    sender_id = actor.user.id if actor.role == "owner" else actor.veterinarian.id
    client_id = payload.client_message_id or uuid.uuid4()
    existing = db.query(models.Message).filter_by(
        consultation_id=consultation_id, client_message_id=client_id
    ).first()
    if existing:
        return existing
    message = models.Message(
        consultation_id=consultation_id,
        sender_type=models.MessageSender.USER if actor.role == "owner" else models.MessageSender.VET,
        sender_id=sender_id,
        content=payload.content,
        attachment_uri=payload.attachment_uri,
        client_message_id=client_id,
        delivered_at=now_bkk(),
    )
    db.add(message)
    consultation.updated_at = now_bkk()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.query(models.Message).filter_by(
            consultation_id=consultation_id, client_message_id=client_id
        ).one()
    db.refresh(message)
    return message


@router.get("/consultations/{consultation_id}/messages", response_model=list[MessageResponse])
def list_messages(
    consultation_id: int,
    after_id: int | None = Query(default=None, ge=1),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    _require_participant(consultation_id, actor, db)
    query = db.query(models.Message).filter_by(consultation_id=consultation_id)
    if after_id:
        query = query.filter(models.Message.id > after_id)
    return query.order_by(models.Message.id).limit(limit).all()


@router.post("/consultations/{consultation_id}/messages/read", status_code=204)
def mark_messages_read(
    consultation_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    _require_participant(consultation_id, actor, db)
    own_type = models.MessageSender.USER if actor.role == "owner" else models.MessageSender.VET
    now = now_bkk()
    db.query(models.Message).filter(
        models.Message.consultation_id == consultation_id,
        models.Message.sender_type != own_type,
        models.Message.read_at.is_(None),
    ).update({models.Message.is_read: True, models.Message.read_at: now}, synchronize_session=False)
    db.commit()


@router.post("/consultations/{consultation_id}/shared-assessments", response_model=SharedAssessmentResponse)
def share_assessment(
    consultation_id: int,
    payload: ShareAssessmentRequest,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    consultation = _require_participant(consultation_id, actor, db)
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="Only the pet owner can share an assessment")
    assessment = db.query(models.HealthAssessment).filter_by(
        id=payload.assessment_id, pet_id=consultation.pet_id
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found for this pet")
    shared = db.query(models.ConsultationSharedAssessment).filter_by(
        consultation_id=consultation_id, assessment_id=assessment.id
    ).first()
    if not shared:
        shared = models.ConsultationSharedAssessment(
            consultation_id=consultation_id,
            assessment_id=assessment.id,
            shared_by_user_id=actor.user.id,
        )
        db.add(shared)
    else:
        shared.revoked_at = None
    db.commit()
    db.refresh(shared)
    return shared


@router.get(
    "/consultations/{consultation_id}/shared-assessments",
    response_model=list[SharedAssessmentDetailResponse],
)
def list_shared_assessments(
    consultation_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
    auth_context: SupabaseAuthContext = Depends(get_supabase_auth_context),
):
    _require_participant(consultation_id, actor, db)
    shared_rows = (
        db.query(models.ConsultationSharedAssessment)
        .options(joinedload(models.ConsultationSharedAssessment.assessment))
        .filter_by(consultation_id=consultation_id, revoked_at=None)
        .order_by(models.ConsultationSharedAssessment.shared_at.desc())
        .all()
    )
    results = []
    for shared in shared_rows:
        assessment = schemas.AssessmentResponse.model_validate(shared.assessment)
        if assessment.image_uri:
            try:
                assessment.image_uri = create_assessment_signed_url(
                    auth_context.access_token, assessment.image_uri
                )
            except Exception:
                assessment.image_uri = None
        results.append(
            SharedAssessmentDetailResponse(
                id=shared.id,
                consultation_id=shared.consultation_id,
                assessment_id=shared.assessment_id,
                shared_at=shared.shared_at,
                revoked_at=shared.revoked_at,
                assessment=assessment,
            )
        )
    return results


@router.delete("/consultations/{consultation_id}/shared-assessments/{assessment_id}", status_code=204)
def revoke_assessment_share(
    consultation_id: int,
    assessment_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    _require_participant(consultation_id, actor, db)
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="Only the pet owner can revoke sharing")
    shared = db.query(models.ConsultationSharedAssessment).filter_by(
        consultation_id=consultation_id, assessment_id=assessment_id
    ).first()
    if not shared:
        raise HTTPException(status_code=404, detail="Shared assessment not found")
    shared.revoked_at = now_bkk()
    db.commit()


@router.post("/consultations/{consultation_id}/appointments", response_model=AppointmentResponse)
def propose_appointment(
    consultation_id: int,
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    consultation = _require_participant(consultation_id, actor, db)
    if actor.role != "vet":
        raise HTTPException(status_code=403, detail="Only the assigned veterinarian can propose appointments")
    if payload.starts_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="starts_at must include a timezone")
    if payload.starts_at <= now_bkk():
        raise HTTPException(status_code=422, detail="starts_at must be in the future")
    if payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    appointment = models.Appointment(
        consultation_id=consultation.id,
        pet_id=consultation.pet_id,
        provider_id=consultation.provider_id,
        proposed_by_vet_id=actor.veterinarian.id,
        **payload.model_dump(),
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.get(
    "/consultations/{consultation_id}/appointments",
    response_model=list[AppointmentResponse],
)
def list_consultation_appointments(
    consultation_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    """List appointment proposals visible to either consultation participant."""
    _require_participant(consultation_id, actor, db)
    return (
        db.query(models.Appointment)
        .filter_by(consultation_id=consultation_id)
        .order_by(models.Appointment.starts_at.desc(), models.Appointment.id.desc())
        .all()
    )


@router.put("/appointments/{appointment_id}/decision", response_model=AppointmentResponse)
def decide_appointment(
    appointment_id: int,
    payload: AppointmentDecision,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    appointment = db.query(models.Appointment).filter_by(id=appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    _require_participant(appointment.consultation_id, actor, db)
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="Only the pet owner can respond")
    if appointment.status != "proposed":
        raise HTTPException(status_code=409, detail="Appointment has already been answered")
    appointment.status = payload.decision
    appointment.responded_at = now_bkk()
    appointment.updated_at = now_bkk()
    _sync_appointment_calendar(appointment, db)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.put("/appointments/{appointment_id}", response_model=AppointmentResponse)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    appointment = db.query(models.Appointment).filter_by(id=appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    _require_participant(appointment.consultation_id, actor, db)
    if actor.role != "vet":
        raise HTTPException(
            status_code=403,
            detail="Only the assigned veterinarian can reschedule appointments",
        )
    if appointment.status not in {"proposed", "accepted"}:
        raise HTTPException(status_code=409, detail="Appointment can no longer be changed")
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="No appointment changes supplied")

    starts_at = payload.starts_at or appointment.starts_at
    ends_at = payload.ends_at if "ends_at" in payload.model_fields_set else appointment.ends_at
    if starts_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="starts_at must include a timezone")
    if starts_at <= now_bkk():
        raise HTTPException(status_code=422, detail="starts_at must be in the future")
    if ends_at is not None:
        if ends_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="ends_at must include a timezone")
        if ends_at <= starts_at:
            raise HTTPException(status_code=422, detail="ends_at must be after starts_at")

    appointment.starts_at = starts_at
    appointment.ends_at = ends_at
    if "reason" in payload.model_fields_set:
        appointment.reason = payload.reason
    appointment.updated_at = now_bkk()
    _sync_appointment_calendar(appointment, db)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.put(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentResponse,
)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    appointment = db.query(models.Appointment).filter_by(id=appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    _require_participant(appointment.consultation_id, actor, db)
    if appointment.status == "cancelled":
        return appointment
    if appointment.status not in {"proposed", "accepted"}:
        raise HTTPException(status_code=409, detail="Appointment can no longer be cancelled")
    appointment.status = "cancelled"
    appointment.updated_at = now_bkk()
    _sync_appointment_calendar(appointment, db)
    db.commit()
    db.refresh(appointment)
    return appointment


@router.post("/consultations/{consultation_id}/ai-summary", response_model=MessageResponse)
def post_ai_summary(
    consultation_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    consultation = _require_participant(consultation_id, actor, db)
    pet = db.query(models.Pet).filter_by(id=consultation.pet_id).one()
    assessment = db.query(models.HealthAssessment).filter(
        models.HealthAssessment.pet_id == pet.id,
        models.HealthAssessment.status == "completed",
    ).order_by(models.HealthAssessment.created_at.desc()).first()
    activities = db.query(models.ActivityLog).filter_by(pet_id=pet.id).order_by(
        models.ActivityLog.created_at.desc()
    ).limit(30).all()
    vaccination = db.query(models.Vaccination).filter_by(pet_id=pet.id).order_by(
        models.Vaccination.date_administered.desc()
    ).first()
    lines = [
        f"AI BRIEFING for {pet.name}",
        f"Latest AI check: {assessment.risk_level.value if assessment and assessment.risk_level else 'n/a'}",
        f"Recent activity: {len(activities)} sessions, {sum(a.duration_minutes or 0 for a in activities):.0f} min total.",
        f"Last vaccination: {vaccination.vaccine_name} on {vaccination.date_administered}" if vaccination else "No vaccination records.",
        "Generated by Petto AI assist - preliminary information, not a diagnosis.",
    ]
    message = models.Message(
        consultation_id=consultation_id,
        sender_type=models.MessageSender.AI,
        message_type="ai",
        content="\n".join(lines),
        delivered_at=now_bkk(),
    )
    db.add(message)
    consultation.updated_at = now_bkk()
    db.commit()
    db.refresh(message)
    return message
