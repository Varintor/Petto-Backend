from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime, timezone, date
from pydantic import BaseModel

from app import models
from app.database import get_db

router = APIRouter(
    prefix="/api/v1",
    tags=["Daily Missions (ภารกิจประจำวัน - Feature 4)"],
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


# Default daily mission set used by the "seed today" helper.
_DEFAULT_MISSIONS = [
    {"title": "Walk for 15 mins", "mission_type": "walk", "target_value": 15, "unit": "minutes", "reward": "50 Treats"},
    {"title": "Water Log", "mission_type": "water", "target_value": 1, "unit": "count", "reward": "20 Treats"},
    {"title": "AI Quick Check", "mission_type": "ai_check", "target_value": 1, "unit": "count", "reward": "100 Treats"},
]


def _require_pet(pet_id: int, db: Session) -> models.Pet:
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")
    return pet


# ==========================================
# Endpoints
# ==========================================
@router.post("/missions", response_model=MissionResponse)
def create_mission(mission: MissionCreate, db: Session = Depends(get_db)):
    """สร้างภารกิจประจำวัน (1 ภารกิจต่อ pet/วัน/ประเภท)"""
    _require_pet(mission.pet_id, db)

    db_mission = models.DailyMission(**mission.model_dump(exclude_none=True))
    db.add(db_mission)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="มีภารกิจประเภทนี้ของวันนี้อยู่แล้ว",
        )
    db.refresh(db_mission)
    return db_mission


@router.get("/pets/{pet_id}/missions", response_model=List[MissionResponse])
def get_pet_missions(
    pet_id: int,
    mission_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """ดูภารกิจของสัตว์เลี้ยง (กรองตามวันได้ด้วย ?mission_date=YYYY-MM-DD)"""
    _require_pet(pet_id, db)

    query = db.query(models.DailyMission).filter(models.DailyMission.pet_id == pet_id)
    if mission_date is not None:
        query = query.filter(models.DailyMission.mission_date == mission_date)

    return query.order_by(
        models.DailyMission.mission_date.desc(),
        models.DailyMission.id.asc(),
    ).all()


@router.get("/pets/{pet_id}/missions/today", response_model=List[MissionResponse])
def get_today_missions(pet_id: int, db: Session = Depends(get_db)):
    """ดูภารกิจของวันนี้"""
    _require_pet(pet_id, db)
    today = datetime.now(timezone.utc).date()
    return db.query(models.DailyMission).filter(
        models.DailyMission.pet_id == pet_id,
        models.DailyMission.mission_date == today,
    ).order_by(models.DailyMission.id.asc()).all()


@router.post("/pets/{pet_id}/missions/seed-today", response_model=List[MissionResponse])
def seed_today_missions(pet_id: int, db: Session = Depends(get_db)):
    """สร้างชุดภารกิจเริ่มต้นของวันนี้ (ข้ามอันที่มีอยู่แล้ว)"""
    _require_pet(pet_id, db)
    today = datetime.now(timezone.utc).date()

    existing_types = {
        m.mission_type
        for m in db.query(models.DailyMission.mission_type).filter(
            models.DailyMission.pet_id == pet_id,
            models.DailyMission.mission_date == today,
        ).all()
    }

    for spec in _DEFAULT_MISSIONS:
        if spec["mission_type"] in existing_types:
            continue
        db.add(models.DailyMission(pet_id=pet_id, mission_date=today, **spec))
    db.commit()

    return db.query(models.DailyMission).filter(
        models.DailyMission.pet_id == pet_id,
        models.DailyMission.mission_date == today,
    ).order_by(models.DailyMission.id.asc()).all()


@router.put("/missions/{mission_id}/complete", response_model=MissionResponse)
def complete_mission(mission_id: int, is_completed: bool = True, db: Session = Depends(get_db)):
    """ทำเครื่องหมายภารกิจสำเร็จ/ยกเลิก"""
    mission = db.query(models.DailyMission).filter(
        models.DailyMission.id == mission_id
    ).first()
    if not mission:
        raise HTTPException(status_code=404, detail="ไม่พบภารกิจในระบบ")

    mission.is_completed = is_completed
    mission.completed_at = datetime.now(timezone.utc) if is_completed else None
    db.commit()
    db.refresh(mission)
    return mission


@router.delete("/missions/{mission_id}")
def delete_mission(mission_id: int, db: Session = Depends(get_db)):
    mission = db.query(models.DailyMission).filter(
        models.DailyMission.id == mission_id
    ).first()
    if not mission:
        raise HTTPException(status_code=404, detail="ไม่พบภารกิจในระบบ")
    db.delete(mission)
    db.commit()
    return {"message": "ลบภารกิจเรียบร้อยแล้ว"}
