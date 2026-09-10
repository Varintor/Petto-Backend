"""Small, protected administration API for veterinarian onboarding.

The first UI for these endpoints is FastAPI's Swagger page.  The static admin
credential is deliberately server-side configuration; it must never be
embedded in the Flutter application.  A future multi-admin portal can replace
this dependency with named admin accounts without changing the resource API.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from supabase import Client, create_client

from app import models
from app.database import get_db


router = APIRouter(prefix="/api/v1/admin", tags=["Administration - Veterinarians"])
logger = logging.getLogger("petto.admin")
admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


def require_admin_key(provided_key: str | None = Depends(admin_key_header)) -> None:
    configured_key = os.getenv("ADMIN_API_KEY", "").strip()
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Veterinarian administration is not configured",
        )
    if not provided_key or not secrets.compare_digest(provided_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credential",
        )


def get_supabase_admin_client() -> Client:
    url = os.getenv("SUPABASE_URL", "").strip()
    service_key = (
        os.getenv("SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if not url or not service_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Veterinarian invitations are not configured",
        )
    return create_client(url, service_key)


class VeterinarianCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str = Field(min_length=1, max_length=200)
    clinic_name: str | None = Field(default=None, max_length=200)
    license_number: str | None = Field(default=None, max_length=100)
    specialty: str | None = Field(default=None, max_length=200)
    avatar_uri: str | None = Field(default=None, max_length=2048)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        local, separator, domain = normalized.partition("@")
        if not separator or not local or "." not in domain:
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name is required")
        return normalized


class VeterinarianUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    clinic_name: str | None = Field(default=None, max_length=200)
    license_number: str | None = Field(default=None, max_length=100)
    specialty: str | None = Field(default=None, max_length=200)
    avatar_uri: str | None = Field(default=None, max_length=2048)
    is_accepting_consultations: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name is required")
        return normalized


class VerificationUpdate(BaseModel):
    verification_status: Literal["pending", "approved", "rejected", "disabled"]


class ProviderAssignment(BaseModel):
    is_active: bool = True
    accepting_consultations: bool = True


class VeterinarianAdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supabase_uid: str | None
    email: str
    name: str
    clinic_name: str | None
    license_number: str | None
    specialty: str | None
    avatar_uri: str | None
    verification_status: str
    is_online: bool
    is_accepting_consultations: bool
    provider_ids: list[int]
    created_at: datetime
    updated_at: datetime | None


def _vet_query(db: Session):
    return db.query(models.Veterinarian).options(
        selectinload(models.Veterinarian.provider_links)
    )


def _vet_response(vet: models.Veterinarian) -> VeterinarianAdminResponse:
    return VeterinarianAdminResponse(
        id=vet.id,
        supabase_uid=vet.supabase_uid,
        email=vet.email,
        name=vet.name,
        clinic_name=vet.clinic_name,
        license_number=vet.license_number,
        specialty=vet.specialty,
        avatar_uri=vet.avatar_uri,
        verification_status=vet.verification_status,
        is_online=vet.is_online,
        is_accepting_consultations=vet.is_accepting_consultations,
        provider_ids=sorted(
            link.provider_id for link in vet.provider_links if link.is_active
        ),
        created_at=vet.created_at,
        updated_at=vet.updated_at,
    )


def _get_vet_or_404(veterinarian_id: int, db: Session) -> models.Veterinarian:
    vet = _vet_query(db).filter(models.Veterinarian.id == veterinarian_id).first()
    if vet is None:
        raise HTTPException(status_code=404, detail="Veterinarian not found")
    return vet


def _commit_or_conflict(db: Session, detail: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from error


@router.get(
    "/veterinarians",
    response_model=list[VeterinarianAdminResponse],
    dependencies=[Depends(require_admin_key)],
)
def list_veterinarians(
    verification_status: Literal["pending", "approved", "rejected", "disabled"]
    | None = None,
    search: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    query = _vet_query(db)
    if verification_status is not None:
        query = query.filter(
            models.Veterinarian.verification_status == verification_status
        )
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        query = query.filter(
            func.lower(models.Veterinarian.name).like(term)
            | func.lower(models.Veterinarian.email).like(term)
        )
    return [_vet_response(vet) for vet in query.order_by(models.Veterinarian.name).all()]


@router.post(
    "/veterinarians",
    response_model=VeterinarianAdminResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_key)],
)
def create_veterinarian(payload: VeterinarianCreate, db: Session = Depends(get_db)):
    duplicate = db.query(models.Veterinarian.id).filter(
        func.lower(models.Veterinarian.email) == payload.email
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Email is already registered")
    vet = models.Veterinarian(
        **payload.model_dump(),
        password_hash=None,
        verification_status="pending",
        is_accepting_consultations=False,
    )
    db.add(vet)
    _commit_or_conflict(db, "Email or license number is already registered")
    vet = _get_vet_or_404(vet.id, db)
    logger.info("Veterinarian record created id=%s", vet.id)
    return _vet_response(vet)


@router.patch(
    "/veterinarians/{veterinarian_id}",
    response_model=VeterinarianAdminResponse,
    dependencies=[Depends(require_admin_key)],
)
def update_veterinarian(
    veterinarian_id: int,
    payload: VeterinarianUpdate,
    db: Session = Depends(get_db),
):
    vet = _get_vet_or_404(veterinarian_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_accepting_consultations") and vet.verification_status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Only an approved veterinarian can accept consultations",
        )
    for name, value in changes.items():
        setattr(vet, name, value.strip() if isinstance(value, str) else value)
    _commit_or_conflict(db, "License number is already registered")
    db.refresh(vet)
    logger.info("Veterinarian record updated id=%s fields=%s", vet.id, sorted(changes))
    return _vet_response(_get_vet_or_404(vet.id, db))


@router.post(
    "/veterinarians/{veterinarian_id}/verification",
    response_model=VeterinarianAdminResponse,
    dependencies=[Depends(require_admin_key)],
)
def update_verification(
    veterinarian_id: int,
    payload: VerificationUpdate,
    db: Session = Depends(get_db),
):
    vet = _get_vet_or_404(veterinarian_id, db)
    vet.verification_status = payload.verification_status
    if payload.verification_status != "approved":
        vet.is_accepting_consultations = False
        for link in vet.provider_links:
            link.accepting_consultations = False
    db.commit()
    db.refresh(vet)
    logger.info(
        "Veterinarian verification changed id=%s status=%s",
        vet.id,
        vet.verification_status,
    )
    return _vet_response(_get_vet_or_404(vet.id, db))


@router.put(
    "/veterinarians/{veterinarian_id}/providers/{provider_id}",
    response_model=VeterinarianAdminResponse,
    dependencies=[Depends(require_admin_key)],
)
def assign_provider(
    veterinarian_id: int,
    provider_id: int,
    payload: ProviderAssignment,
    db: Session = Depends(get_db),
):
    vet = _get_vet_or_404(veterinarian_id, db)
    provider = db.query(models.VeterinaryProvider).filter_by(id=provider_id).first()
    if provider is None or provider.provider_status == "disabled":
        raise HTTPException(status_code=404, detail="Veterinary provider not found")
    if payload.accepting_consultations and vet.verification_status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Approve the veterinarian before enabling consultations",
        )
    link = db.query(models.ProviderVeterinarian).filter_by(
        provider_id=provider_id,
        veterinarian_id=veterinarian_id,
    ).first()
    if link is None:
        link = models.ProviderVeterinarian(
            provider_id=provider_id,
            veterinarian_id=veterinarian_id,
        )
        db.add(link)
    link.is_active = payload.is_active
    link.accepting_consultations = (
        payload.is_active and payload.accepting_consultations
    )
    db.flush()
    vet.is_accepting_consultations = (
        db.query(models.ProviderVeterinarian)
        .filter(
            models.ProviderVeterinarian.veterinarian_id == veterinarian_id,
            models.ProviderVeterinarian.is_active.is_(True),
            models.ProviderVeterinarian.accepting_consultations.is_(True),
        )
        .first()
        is not None
    )
    db.commit()
    logger.info(
        "Veterinarian assigned id=%s provider_id=%s accepting=%s",
        vet.id,
        provider.id,
        link.accepting_consultations,
    )
    return _vet_response(_get_vet_or_404(vet.id, db))


@router.post(
    "/veterinarians/{veterinarian_id}/invite",
    response_model=VeterinarianAdminResponse,
    dependencies=[Depends(require_admin_key)],
)
def invite_veterinarian(
    veterinarian_id: int,
    db: Session = Depends(get_db),
):
    vet = _get_vet_or_404(veterinarian_id, db)
    if vet.supabase_uid:
        raise HTTPException(status_code=409, detail="Veterinarian already has an Auth account")
    redirect_to = os.getenv("VET_INVITE_REDIRECT_URL", "").strip()
    if not redirect_to:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Veterinarian invitation redirect is not configured",
        )
    options = {
        "data": {"petto_invited_vet": True, "name": vet.name},
        "redirect_to": redirect_to,
    }
    try:
        response = get_supabase_admin_client().auth.admin.invite_user_by_email(
            vet.email,
            options,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("Veterinarian invitation failed id=%s", vet.id)
        raise HTTPException(
            status_code=502,
            detail="Supabase could not send the veterinarian invitation",
        ) from error
    invited_user = getattr(response, "user", None)
    invited_uid = getattr(invited_user, "id", None)
    if not invited_uid:
        raise HTTPException(
            status_code=502,
            detail="Supabase invitation did not return an Auth user",
        )
    vet.supabase_uid = str(invited_uid)
    db.commit()
    db.refresh(vet)
    logger.info("Veterinarian invited id=%s", vet.id)
    return _vet_response(_get_vet_or_404(vet.id, db))
