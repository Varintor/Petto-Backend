# -*- coding: utf-8 -*-
"""Feature 5: Health History Review.

One unified, reverse-chronological timeline of everything recorded for a pet
(AI assessments, activities, vaccinations, completed missions) so the owner -
and later the vet - can review the health record in one place.
"""
from datetime import datetime, date, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, require_owned_pet
from app.database import get_db
from app.utils.time import BANGKOK_TZ

router = APIRouter(prefix="/api/v1", tags=["Health History"])

VALID_TYPES = {"assessment", "activity", "vaccination", "mission"}


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

    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return HistoryResponse(pet_id=pet_id, entries=entries[:limit])
