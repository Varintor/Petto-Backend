from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, require_owned_pet
from app.database import get_db
from app.utils.time import now_bkk

router = APIRouter(prefix="/api/v1", tags=["Calendar"])


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    event_type: Literal["care", "medication", "vet", "grooming", "walk"]
    event_date: date
    starts_at: datetime | None = None
    reminder_minutes: int | None = Field(default=30, ge=0, le=10080)

    @model_validator(mode="after")
    def starts_on_event_date(self):
        if self.starts_at and self.starts_at.date() != self.event_date:
            raise ValueError("starts_at must fall on event_date")
        return self


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    event_type: Literal["care", "medication", "vet", "grooming", "walk"] | None = None
    event_date: date | None = None
    starts_at: datetime | None = None
    reminder_minutes: int | None = Field(default=None, ge=0, le=10080)
    is_completed: bool | None = None


class CalendarEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    title: str
    event_type: str
    event_date: date
    starts_at: datetime | None
    is_completed: bool
    reminder_minutes: int | None
    appointment_id: int | None
    created_at: datetime
    updated_at: datetime


def _owned_event(event_id: int, user: models.User, db: Session) -> models.CalendarEvent:
    event = db.query(models.CalendarEvent).filter_by(id=event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Calendar event not found")
    require_owned_pet(event.pet_id, user, db)
    return event


@router.get("/pets/{pet_id}/calendar-events", response_model=list[CalendarEventResponse])
def list_calendar_events(
    pet_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, user, db)
    query = db.query(models.CalendarEvent).filter_by(pet_id=pet_id)
    if date_from:
        query = query.filter(models.CalendarEvent.event_date >= date_from)
    if date_to:
        query = query.filter(models.CalendarEvent.event_date <= date_to)
    return query.order_by(models.CalendarEvent.event_date, models.CalendarEvent.starts_at).limit(limit).all()


@router.post("/pets/{pet_id}/calendar-events", response_model=CalendarEventResponse)
def create_calendar_event(
    pet_id: int,
    payload: CalendarEventCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, user, db)
    event = models.CalendarEvent(pet_id=pet_id, **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.patch("/calendar-events/{event_id}", response_model=CalendarEventResponse)
def update_calendar_event(
    event_id: int,
    payload: CalendarEventUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    event = _owned_event(event_id, user, db)
    if event.appointment_id is not None:
        raise HTTPException(status_code=409, detail="Appointment events must be changed through consultation")
    values = payload.model_dump(exclude_unset=True)
    resulting_date = values.get("event_date", event.event_date)
    resulting_start = values.get("starts_at", event.starts_at)
    if resulting_start and resulting_start.date() != resulting_date:
        raise HTTPException(status_code=422, detail="starts_at must fall on event_date")
    for key, value in values.items():
        setattr(event, key, value)
    event.updated_at = now_bkk()
    db.commit()
    db.refresh(event)
    return event


@router.delete("/calendar-events/{event_id}", status_code=204)
def delete_calendar_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    event = _owned_event(event_id, user, db)
    if event.appointment_id is not None:
        raise HTTPException(status_code=409, detail="Appointment events must be changed through consultation")
    db.delete(event)
    db.commit()

