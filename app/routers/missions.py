import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime, date
from pydantic import BaseModel

from app import models
from app.database import get_db
from app.auth import get_current_user, require_owned_pet
from app.utils.time import now_bkk, today_bkk

router = APIRouter(
    prefix="/api/v1",
    tags=["Daily Missions"],
)


# ==========================================
# Schemas
# ==========================================
class MissionCreate(BaseModel):
    pet_id: int
    title: str
    mission_type: str = "walk"      # walk | water | ai_check | ...
    target_value: Optional[float] = None
    unit: Optional[str] = None      # minutes | count | meters
    reward: Optional[str] = None
    mission_date: Optional[date] = None  # defaults to today (DB CURRENT_DATE)


class MissionResponse(BaseModel):
    id: int
    pet_id: int
    mission_date: date
    title: str
    mission_type: str
    target_value: Optional[float] = None
    unit: Optional[str] = None
    reward: Optional[str] = None
    is_completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Core missions (always included daily)
_CORE_MISSIONS = [
    {"title": "Walk for 15 minutes", "mission_type": "walk", "target_value": 15, "unit": "minutes", "reward": "50 Treats"},
    {"title": "Fresh water refill", "mission_type": "water", "target_value": 1, "unit": "count", "reward": "20 Treats"},
    {"title": "AI health check", "mission_type": "ai_check", "target_value": 1, "unit": "count", "reward": "100 Treats"},
]

# Rotating bonus missions (2 picked randomly each day)
_BONUS_MISSIONS = [
    {"title": "Brush your pet's fur", "mission_type": "grooming", "target_value": 1, "unit": "count", "reward": "30 Treats"},
    {"title": "5-minute play session", "mission_type": "play", "target_value": 5, "unit": "minutes", "reward": "40 Treats"},
    {"title": "Take a cute photo", "mission_type": "photo", "target_value": 1, "unit": "count", "reward": "25 Treats"},
    {"title": "Teeth check", "mission_type": "dental_check", "target_value": 1, "unit": "count", "reward": "35 Treats"},
    {"title": "Nail trim check", "mission_type": "nail_check", "target_value": 1, "unit": "count", "reward": "30 Treats"},
    {"title": "Ear cleaning check", "mission_type": "ear_check", "target_value": 1, "unit": "count", "reward": "30 Treats"},
    {"title": "Weigh your pet", "mission_type": "weight_log", "target_value": 1, "unit": "count", "reward": "40 Treats"},
    {"title": "10-minute cuddle time", "mission_type": "bonding", "target_value": 10, "unit": "minutes", "reward": "35 Treats"},
    {"title": "Train a new trick", "mission_type": "training", "target_value": 1, "unit": "count", "reward": "60 Treats"},
    {"title": "Check food portion", "mission_type": "feeding_check", "target_value": 1, "unit": "count", "reward": "25 Treats"},
    {"title": "Eye and nose check", "mission_type": "eye_nose_check", "target_value": 1, "unit": "count", "reward": "30 Treats"},
    {"title": "Socialization time", "mission_type": "social", "target_value": 1, "unit": "count", "reward": "45 Treats"},
]

# Stable IDs shared with the Flutter wardrobe catalogue. Persisting mission
# row IDs here made valid rewards invisible to the client after a restart.
_MISSION_ACCESSORY_MAP = {
    "walk": "acc_hat",
    "water": "acc_water_bowl",
    "ai_check": "acc_doctor_coat",
    "grooming": "acc_brush",
    "play": "acc_ball",
    "photo": "acc_camera",
    "dental_check": "acc_toothbrush",
    "nail_check": "acc_nail_file",
    "ear_check": "acc_ear_tag",
    "weight_log": "acc_scale",
    "bonding": "acc_heart",
    "training": "acc_diploma",
    "feeding_check": "acc_bowl",
    "eye_nose_check": "acc_glasses",
    "social": "acc_friendship",
}


def _require_owned_mission(mission_id: int, current_user: models.User, db: Session) -> models.DailyMission:
    """Return the mission only if it exists and its pet belongs to the caller."""
    mission = db.query(models.DailyMission).filter(
        models.DailyMission.id == mission_id
    ).first()
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    require_owned_pet(mission.pet_id, current_user, db)
    return mission


# ==========================================
# Endpoints
# ==========================================
@router.post("/missions", response_model=MissionResponse)
def create_mission(
    mission: MissionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a daily mission (one per pet/day/type)."""
    require_owned_pet(mission.pet_id, current_user, db)

    db_mission = models.DailyMission(**mission.model_dump(exclude_none=True))
    db.add(db_mission)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A mission of this type already exists for today",
        )
    db.refresh(db_mission)
    return db_mission


@router.get("/pets/{pet_id}/missions", response_model=List[MissionResponse])
def get_pet_missions(
    pet_id: int,
    mission_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List missions for a pet. Filter by date with ?mission_date=YYYY-MM-DD."""
    require_owned_pet(pet_id, current_user, db)

    query = db.query(models.DailyMission).filter(models.DailyMission.pet_id == pet_id)
    if mission_date is not None:
        query = query.filter(models.DailyMission.mission_date == mission_date)

    return query.order_by(
        models.DailyMission.mission_date.desc(),
        models.DailyMission.id.asc(),
    ).all()


@router.get("/pets/{pet_id}/missions/today", response_model=List[MissionResponse])
def get_today_missions(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get today's missions for a pet."""
    require_owned_pet(pet_id, current_user, db)
    # Bangkok date, matching activities.py's walk-mission auto-complete.
    # (Using UTC here made "today" disagree with the auto-complete between
    # 00:00-07:00 ICT, so a finished walk couldn't find its mission.)
    today = today_bkk()
    return db.query(models.DailyMission).filter(
        models.DailyMission.pet_id == pet_id,
        models.DailyMission.mission_date == today,
    ).order_by(models.DailyMission.id.asc()).all()


@router.post("/pets/{pet_id}/missions/seed-today", response_model=List[MissionResponse])
def seed_today_missions(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Seed today's missions: 3 core + 2 random bonus (skips duplicates)."""
    require_owned_pet(pet_id, current_user, db)
    today = today_bkk()

    existing_types = {
        m.mission_type
        for m in db.query(models.DailyMission.mission_type).filter(
            models.DailyMission.pet_id == pet_id,
            models.DailyMission.mission_date == today,
        ).all()
    }

    day_seed = int(today.strftime("%Y%m%d")) + pet_id
    rng = random.Random(day_seed)
    bonus_picks = rng.sample(_BONUS_MISSIONS, k=min(2, len(_BONUS_MISSIONS)))
    all_missions = _CORE_MISSIONS + bonus_picks

    for spec in all_missions:
        if spec["mission_type"] in existing_types:
            continue
        db.add(models.DailyMission(pet_id=pet_id, mission_date=today, **spec))
    db.commit()

    return db.query(models.DailyMission).filter(
        models.DailyMission.pet_id == pet_id,
        models.DailyMission.mission_date == today,
    ).order_by(models.DailyMission.id.asc()).all()


@router.put("/missions/{mission_id}/complete", response_model=MissionResponse)
def complete_mission(
    mission_id: int,
    is_completed: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mark a mission as completed or undo completion (owner only)."""
    mission = _require_owned_mission(mission_id, current_user, db)

    mission.is_completed = is_completed
    mission.completed_at = now_bkk() if is_completed else None
    if is_completed:
        # Rewards are append-only: undoing a mission does not remove an item
        # the owner has already earned. The unique key makes retries safe.
        accessory_id = _MISSION_ACCESSORY_MAP.get(mission.mission_type)
        if accessory_id is not None:
            exists = db.query(models.PetWardrobeItem).filter_by(
                pet_id=mission.pet_id, accessory_id=accessory_id
            ).first()
            if not exists:
                db.add(models.PetWardrobeItem(
                    pet_id=mission.pet_id,
                    accessory_id=accessory_id,
                ))
    db.commit()
    db.refresh(mission)
    return mission


@router.delete("/missions/{mission_id}")
def delete_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    mission = _require_owned_mission(mission_id, current_user, db)
    db.delete(mission)
    db.commit()
    return {"message": "Mission deleted"}
