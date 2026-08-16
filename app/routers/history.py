# -*- coding: utf-8 -*-
"""Feature 5: Health History Review.

One unified, reverse-chronological timeline of everything recorded for a pet
(AI assessments, activities, vaccinations, completed missions) so the owner -
and later the vet - can review the health record in one place.
"""
from datetime import datetime, date, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app import models
from app.auth import AuthenticatedActor, get_current_actor, get_current_user, require_owned_pet
from app.database import get_db
from app.utils.time import BANGKOK_TZ

router = APIRouter(prefix="/api/v1", tags=["Health History"])

VALID_TYPES = {"assessment", "activity", "vaccination", "mission", "appointment"}


class HistoryEntry(BaseModel):
    type: str                      # assessment | activity | vaccination | mission
    ref_id: int                    # id of the underlying row
    timestamp: datetime
    title: str
    summary: Optional[str] = None
    risk_level: Optional[str] = None   # assessments only
    status: Optional[str] = None       # assessments only
    error_code: Optional[str] = None   # failed assessments only


class HistoryResponse(BaseModel):
    pet_id: int
    entries: List[HistoryEntry]


class HealthProfileUpdate(BaseModel):
    allergies: list[str] = Field(default_factory=list, max_length=100)
    chronic_conditions: list[str] = Field(default_factory=list, max_length=100)
    current_medications: list[str] = Field(default_factory=list, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)


class HealthProfileResponse(HealthProfileUpdate):
    model_config = ConfigDict(from_attributes=True)
    pet_id: int
    updated_at: datetime


class HealthCardDTO(BaseModel):
    pet_id: int
    name: str
    species: str | None
    breed: str | None
    gender: str | None
    date_of_birth: date | None
    weight_kg: float | None
    blood_type: str | None
    allergies: list[str]
    chronic_conditions: list[str]
    current_medications: list[str]
    notes: str | None
    latest_assessment: HistoryEntry | None
    latest_vaccination: HistoryEntry | None
    recent_activity: HistoryEntry | None
    generated_at: datetime


class SharedHealthCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    consultation_id: int
    pet_id: int
    snapshot: dict
    shared_at: datetime
    revoked_at: datetime | None


def _health_card(pet: models.Pet, db: Session) -> HealthCardDTO:
    profile = db.query(models.PetHealthProfile).filter_by(pet_id=pet.id).first()
    assessment = db.query(models.HealthAssessment).filter_by(pet_id=pet.id).order_by(
        models.HealthAssessment.created_at.desc()
    ).first()
    vaccination = db.query(models.Vaccination).filter_by(pet_id=pet.id).order_by(
        models.Vaccination.date_administered.desc()
    ).first()
    activity = db.query(models.ActivityLog).filter_by(pet_id=pet.id).order_by(
        models.ActivityLog.created_at.desc()
    ).first()
    assessment_entry = None if not assessment else HistoryEntry(
        type="assessment", ref_id=assessment.id, timestamp=assessment.created_at,
        title="AI Health Check", summary=(assessment.symptom_description or "")[:120],
        risk_level=assessment.risk_level.value if assessment.risk_level else None,
        status=assessment.status, error_code=assessment.error_code,
    )
    vaccination_entry = None if not vaccination else HistoryEntry(
        type="vaccination", ref_id=vaccination.id, timestamp=vaccination.created_at,
        title=f"Vaccination: {vaccination.vaccine_name}",
        summary=f"Administered {vaccination.date_administered}",
    )
    activity_entry = None if not activity else HistoryEntry(
        type="activity", ref_id=activity.id, timestamp=activity.created_at,
        title=f"{activity.activity_type.capitalize()} session",
        summary=f"{activity.duration_minutes:.0f} min, {(activity.distance_meters or 0) / 1000:.2f} km",
    )
    return HealthCardDTO(
        pet_id=pet.id, name=pet.name, species=pet.species, breed=pet.breed,
        gender=pet.gender, date_of_birth=pet.date_of_birth,
        weight_kg=float(pet.weight_kg) if pet.weight_kg is not None else None,
        blood_type=pet.blood_type,
        allergies=profile.allergies if profile else [],
        chronic_conditions=profile.chronic_conditions if profile else [],
        current_medications=profile.current_medications if profile else [],
        notes=profile.notes if profile else None,
        latest_assessment=assessment_entry,
        latest_vaccination=vaccination_entry,
        recent_activity=activity_entry,
        generated_at=datetime.now(tz=BANGKOK_TZ),
    )


def _participant_consultation(
    consultation_id: int, actor: AuthenticatedActor, db: Session
) -> models.Consultation:
    consultation = db.query(models.Consultation).filter_by(id=consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    pet = db.query(models.Pet).filter_by(id=consultation.pet_id).first()
    owner_ok = actor.role == "owner" and pet and pet.user_id == actor.user.id
    vet_ok = actor.role == "vet" and consultation.vet_id == actor.veterinarian.id
    if not (owner_ok or vet_ok):
        raise HTTPException(status_code=404, detail="Consultation not found")
    return consultation


@router.get("/pets/{pet_id}/health-profile", response_model=HealthProfileResponse)
def get_health_profile(
    pet_id: int,
    db: Session = Depends(get_db),
    owner: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, owner, db)
    profile = db.query(models.PetHealthProfile).filter_by(pet_id=pet_id).first()
    if not profile:
        profile = models.PetHealthProfile(
            pet_id=pet_id, allergies=[], chronic_conditions=[], current_medications=[]
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.put("/pets/{pet_id}/health-profile", response_model=HealthProfileResponse)
def update_health_profile(
    pet_id: int,
    payload: HealthProfileUpdate,
    db: Session = Depends(get_db),
    owner: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, owner, db)
    profile = db.query(models.PetHealthProfile).filter_by(pet_id=pet_id).first()
    if not profile:
        profile = models.PetHealthProfile(pet_id=pet_id)
        db.add(profile)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    profile.updated_at = datetime.now(tz=BANGKOK_TZ)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/pets/{pet_id}/health-card", response_model=HealthCardDTO)
def get_health_card(
    pet_id: int,
    db: Session = Depends(get_db),
    owner: models.User = Depends(get_current_user),
):
    pet = require_owned_pet(pet_id, owner, db)
    return _health_card(pet, db)


@router.post("/consultations/{consultation_id}/shared-health-cards", response_model=SharedHealthCardResponse)
def share_health_card(
    consultation_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    consultation = _participant_consultation(consultation_id, actor, db)
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="Only the pet owner can share a health card")
    pet = db.query(models.Pet).filter_by(id=consultation.pet_id).one()
    shared = models.ConsultationSharedHealthCard(
        consultation_id=consultation.id, pet_id=pet.id,
        shared_by_user_id=actor.user.id,
        snapshot=_health_card(pet, db).model_dump(mode="json"),
    )
    db.add(shared)
    db.commit()
    db.refresh(shared)
    return shared


@router.get("/consultations/{consultation_id}/shared-health-cards", response_model=list[SharedHealthCardResponse])
def list_shared_health_cards(
    consultation_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    _participant_consultation(consultation_id, actor, db)
    return db.query(models.ConsultationSharedHealthCard).filter_by(
        consultation_id=consultation_id, revoked_at=None
    ).order_by(models.ConsultationSharedHealthCard.shared_at.desc()).all()


@router.delete(
    "/consultations/{consultation_id}/shared-health-cards/{shared_card_id}",
    status_code=204,
)
def revoke_shared_health_card(
    consultation_id: int,
    shared_card_id: int,
    db: Session = Depends(get_db),
    actor: AuthenticatedActor = Depends(get_current_actor),
):
    """Let the pet owner stop future access to a shared health-card snapshot."""
    _participant_consultation(consultation_id, actor, db)
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="Only the pet owner can revoke a health card")
    shared = db.query(models.ConsultationSharedHealthCard).filter_by(
        id=shared_card_id,
        consultation_id=consultation_id,
        shared_by_user_id=actor.user.id,
        revoked_at=None,
    ).first()
    if not shared:
        raise HTTPException(status_code=404, detail="Shared health card not found")
    shared.revoked_at = datetime.now(tz=BANGKOK_TZ)
    db.commit()


@router.get("/pets/{pet_id}/history", response_model=HistoryResponse)
def get_pet_history(
    pet_id: int,
    types: Optional[str] = Query(None, description="Comma list: assessment,activity,vaccination,mission"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Unified health timeline for a pet, newest first (owner only)."""
    require_owned_pet(pet_id, current_user, db)

    wanted = VALID_TYPES if not types else (
        {t.strip() for t in types.split(",")} & VALID_TYPES
    )
    entries: List[HistoryEntry] = []

    def bounded_rows(query, timestamp_column):
        """Apply the timeline window and cap rows before loading them.

        Fetching at most ``limit`` rows per type is sufficient to calculate the
        global top ``limit``: no individual type can contribute more than that
        many rows to the final merged page.
        """
        if date_from:
            start = datetime.combine(date_from, time.min, tzinfo=BANGKOK_TZ)
            query = query.filter(timestamp_column >= start)
        if date_to:
            end_exclusive = datetime.combine(
                date_to + timedelta(days=1), time.min, tzinfo=BANGKOK_TZ
            )
            query = query.filter(timestamp_column < end_exclusive)
        return query.order_by(timestamp_column.desc()).limit(limit).all()

    if "assessment" in wanted:
        query = db.query(models.HealthAssessment).filter_by(pet_id=pet_id)
        for a in bounded_rows(query, models.HealthAssessment.created_at):
            snippet = (a.symptom_description or "")[:120]
            entries.append(HistoryEntry(
                type="assessment", ref_id=a.id, timestamp=a.created_at,
                title="AI Health Check", summary=snippet,
                risk_level=a.risk_level.value if a.risk_level else None,
                status=a.status,
                error_code=a.error_code,
            ))

    if "activity" in wanted:
        query = db.query(models.ActivityLog).filter_by(pet_id=pet_id)
        for act in bounded_rows(query, models.ActivityLog.created_at):
            entries.append(HistoryEntry(
                type="activity", ref_id=act.id, timestamp=act.created_at,
                title=f"{act.activity_type.capitalize()} session",
                summary=(f"{act.duration_minutes:.0f} min, "
                         f"{(act.distance_meters or 0) / 1000:.2f} km ({act.source.value})"),
            ))

    if "vaccination" in wanted:
        query = db.query(models.Vaccination).filter_by(pet_id=pet_id)
        for v in bounded_rows(query, models.Vaccination.created_at):
            due = f"; next due {v.next_due_date}" if v.next_due_date else ""
            entries.append(HistoryEntry(
                type="vaccination", ref_id=v.id, timestamp=v.created_at,
                title=f"Vaccination: {v.vaccine_name}",
                summary=f"Administered {v.date_administered}{due}",
            ))

    if "mission" in wanted:
        query = db.query(models.DailyMission).filter(
            models.DailyMission.pet_id == pet_id,
            models.DailyMission.is_completed.is_(True),
            models.DailyMission.completed_at.isnot(None),
        )
        for m in bounded_rows(query, models.DailyMission.completed_at):
            entries.append(HistoryEntry(
                type="mission", ref_id=m.id, timestamp=m.completed_at,
                title=f"Mission completed: {m.title}",
                summary=m.reward,
            ))

    if "appointment" in wanted:
        query = db.query(models.Appointment).filter(
            models.Appointment.pet_id == pet_id,
            models.Appointment.status.in_(("accepted", "completed")),
        )
        for appointment in bounded_rows(query, models.Appointment.starts_at):
            entries.append(HistoryEntry(
                type="appointment", ref_id=appointment.id,
                timestamp=appointment.starts_at,
                title="Veterinary appointment", summary=appointment.reason,
                status=appointment.status,
            ))

    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return HistoryResponse(pet_id=pet_id, entries=entries[:limit])
