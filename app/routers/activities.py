from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from pydantic import BaseModel

from app import models
from app.database import get_db
from app.utils.time import now_bkk

router = APIRouter(
    prefix="/api/v1",
    tags=["Activities"],
)


# ==========================================
# Schemas
# ==========================================

class ActivityCreate(BaseModel):
    pet_id: int
    mission_id: int | None = None
    activity_type: str  # walking, running, playing, resting, feeding
    duration_minutes: float
    distance_meters: float = 0.0
    calories_burned: float | None = None
    avg_speed_kmh: float | None = None
    max_speed_kmh: float | None = None
    steps: int | None = None
    # Per proposal §3.7: raw GPS is processed on-device only and never persisted.
    # We accept only aggregated metrics (distance/duration/etc.), not the route.
    notes: str | None = None
    is_mission_completed: bool = False
    started_at: datetime | None = None
    ended_at: datetime | None = None

class ActivityResponse(BaseModel):
    id: int
    pet_id: int
    mission_id: int | None = None
    activity_type: str
    duration_minutes: float
    distance_meters: float
    calories_burned: float | None = None
    avg_speed_kmh: float | None = None
    max_speed_kmh: float | None = None
    steps: int | None = None
    notes: str | None = None
    is_mission_completed: bool
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True

class ActivityStatsResponse(BaseModel):
    total_activities: int
    total_duration_minutes: float
    total_distance_meters: float
    total_calories: float
    total_steps: int
    completed_missions: int
    avg_daily_distance_meters: float
    avg_daily_duration_minutes: float


# ==========================================
# Activity Endpoints
# ==========================================

@router.post("/activities", response_model=ActivityResponse)
def create_activity(activity: ActivityCreate, db: Session = Depends(get_db)):
    """Record a pet activity session (walk, run, play, etc.)."""
    pet = db.query(models.Pet).filter(models.Pet.id == activity.pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    data = activity.model_dump(exclude_none=True)
    if activity.calories_burned is None and activity.duration_minutes > 0:
        weight = float(pet.weight_kg) if pet.weight_kg else 5.0
        met = {"walking": 3.0, "running": 6.0, "playing": 4.0}.get(activity.activity_type, 3.0)
        data["calories_burned"] = round(met * weight * (activity.duration_minutes / 60), 1)

    db_activity = models.ActivityLog(**data)
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)

    return db_activity


@router.get("/activities", response_model=List[ActivityResponse])
def get_all_activities(db: Session = Depends(get_db)):
    """List all activities."""
    activities = db.query(models.ActivityLog).order_by(
        models.ActivityLog.created_at.desc()
    ).all()
    return activities


@router.get("/pets/{pet_id}/activities", response_model=List[ActivityResponse])
def get_pet_activities(pet_id: int, db: Session = Depends(get_db)):
    """List all activities for a specific pet."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    activities = db.query(models.ActivityLog).filter(
        models.ActivityLog.pet_id == pet_id
    ).order_by(
        models.ActivityLog.created_at.desc()
    ).all()

    return activities


@router.get("/pets/{pet_id}/activities/today", response_model=List[ActivityResponse])
def get_today_activities(pet_id: int, db: Session = Depends(get_db)):
    """List all of today's activities for a pet."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    today_start = now_bkk().replace(hour=0, minute=0, second=0, microsecond=0)

    return db.query(models.ActivityLog).filter(
        models.ActivityLog.pet_id == pet_id,
        models.ActivityLog.created_at >= today_start
    ).order_by(models.ActivityLog.created_at.desc()).all()


@router.get("/pets/{pet_id}/activities/stats", response_model=ActivityStatsResponse)
def get_activity_stats(pet_id: int, db: Session = Depends(get_db)):
    """Aggregated activity statistics for a pet (useful for vet reports)."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    stats = db.query(
        func.count(models.ActivityLog.id).label('total'),
        func.sum(models.ActivityLog.duration_minutes).label('total_duration'),
        func.sum(models.ActivityLog.distance_meters).label('total_distance'),
        func.sum(models.ActivityLog.calories_burned).label('total_calories'),
        func.sum(models.ActivityLog.steps).label('total_steps'),
        func.sum(models.ActivityLog.is_mission_completed.cast(Integer)).label('completed'),
        func.count(func.distinct(func.date(models.ActivityLog.created_at))).label('active_days'),
    ).filter(
        models.ActivityLog.pet_id == pet_id
    ).first()

    active_days = max(stats.active_days or 1, 1)

    return ActivityStatsResponse(
        total_activities=stats.total or 0,
        total_duration_minutes=float(stats.total_duration or 0),
        total_distance_meters=float(stats.total_distance or 0),
        total_calories=float(stats.total_calories or 0),
        total_steps=int(stats.total_steps or 0),
        completed_missions=int(stats.completed or 0),
        avg_daily_distance_meters=round(float(stats.total_distance or 0) / active_days, 1),
        avg_daily_duration_minutes=round(float(stats.total_duration or 0) / active_days, 1),
    )


@router.put("/activities/{activity_id}", response_model=ActivityResponse)
def update_activity(activity_id: int, is_completed: bool = True, db: Session = Depends(get_db)):
    """Update activity mission completion status."""
    activity = db.query(models.ActivityLog).filter(
        models.ActivityLog.id == activity_id
    ).first()

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity.is_mission_completed = is_completed
    db.commit()
    db.refresh(activity)

    return activity


@router.delete("/activities/{activity_id}")
def delete_activity(activity_id: int, db: Session = Depends(get_db)):
    """Delete an activity."""
    activity = db.query(models.ActivityLog).filter(
        models.ActivityLog.id == activity_id
    ).first()

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    db.delete(activity)
    db.commit()

    return {"message": "Activity deleted"}
