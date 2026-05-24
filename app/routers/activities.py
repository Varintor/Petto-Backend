from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from pydantic import BaseModel

from app import models
from app.database import get_db

router = APIRouter(
    prefix="/api/v1",
    tags=["Activities (กิจกรรม/ GPS Tracking)"]
)


# ==========================================
# Schemas
# ==========================================

class ActivityCreate(BaseModel):
    pet_id: int
    activity_type: str  # "walking", "running", "playing"
    duration_minutes: float
    distance_meters: float
    is_mission_completed: bool = False

class ActivityResponse(BaseModel):
    id: int
    pet_id: int
    activity_type: str
    duration_minutes: float
    distance_meters: float
    is_mission_completed: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ActivityStatsResponse(BaseModel):
    total_activities: int
    total_duration_minutes: float
    total_distance_meters: float
    completed_missions: int


# ==========================================
# Activity Endpoints
# ==========================================

@router.post("/activities", response_model=ActivityResponse)
def create_activity(activity: ActivityCreate, db: Session = Depends(get_db)):
    """
    บันทึกกิจกรรม (GPS Tracking)

    หมายเหตุ: ข้อมูลพิกัด GPS ดิบจะไม่ถูกบันทึกตามนโยบายความเป็นส่วนตัว
    จะบันทึกเฉพาะ aggregate data (ระยะทาง, เวลา, ประเภทกิจกรรม)
    """
    # ตรวจสอบว่ามีสัตว์เลี้ยงหรือไม่
    pet = db.query(models.Pet).filter(models.Pet.id == activity.pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    db_activity = models.ActivityLog(**activity.model_dump())
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)

    return db_activity


@router.get("/activities", response_model=List[ActivityResponse])
def get_all_activities(db: Session = Depends(get_db)):
    """
    ดูกิจกรรมทั้งหมดในระบบ
    """
    activities = db.query(models.ActivityLog).order_by(
        models.ActivityLog.created_at.desc()
    ).all()
    return activities


@router.get("/pets/{pet_id}/activities", response_model=List[ActivityResponse])
def get_pet_activities(pet_id: int, db: Session = Depends(get_db)):
    """
    ดูประวัติกิจกรรมทั้งหมดของสัตว์เลี้ยงตัวหนึ่ง
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    activities = db.query(models.ActivityLog).filter(
        models.ActivityLog.pet_id == pet_id
    ).order_by(
        models.ActivityLog.created_at.desc()
    ).all()

    return activities


@router.get("/pets/{pet_id}/activities/today", response_model=ActivityResponse)
def get_today_activity(pet_id: int, db: Session = Depends(get_db)):
    """
    ดูกิจกรรมวันนี้ของสัตว์เลี้ยง
    """
    from sqlalchemy import func

    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    # หากิจกรรมล่าสุดของวันนี้
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    activity = db.query(models.ActivityLog).filter(
        models.ActivityLog.pet_id == pet_id,
        models.ActivityLog.created_at >= today_start
    ).order_by(
        models.ActivityLog.created_at.desc()
    ).first()

    if not activity:
        # ถ้าไม่มีกิจกรรมวันนี้ สร้างตัวเปล่าๆ ส่งกลับ
        return ActivityResponse(
            id=0,
            pet_id=pet_id,
            activity_type="none",
            duration_minutes=0.0,
            distance_meters=0.0,
            is_mission_completed=False,
            created_at=datetime.now()
        )

    return activity


@router.get("/pets/{pet_id}/activities/stats", response_model=ActivityStatsResponse)
def get_activity_stats(pet_id: int, db: Session = Depends(get_db)):
    """
    ดูสถิติกิจกรรมรวมของสัตว์เลี้ยง
    """
    from sqlalchemy import func

    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    # คำนวณสถิติ
    stats = db.query(
        func.count(models.ActivityLog.id).label('total'),
        func.sum(models.ActivityLog.duration_minutes).label('total_duration'),
        func.sum(models.ActivityLog.distance_meters).label('total_distance'),
        func.sum(models.ActivityLog.is_mission_completed.cast(Integer)).label('completed')
    ).filter(
        models.ActivityLog.pet_id == pet_id
    ).first()

    return ActivityStatsResponse(
        total_activities=stats.total or 0,
        total_duration_minutes=float(stats.total_duration or 0),
        total_distance_meters=float(stats.total_distance or 0),
        completed_missions=int(stats.completed or 0)
    )


@router.put("/activities/{activity_id}", response_model=ActivityResponse)
def update_activity(activity_id: int, is_completed: bool = True, db: Session = Depends(get_db)):
    """
    อัปเดตสถานะภารกิจ (ให้สำเร็จ)
    """
    activity = db.query(models.ActivityLog).filter(
        models.ActivityLog.id == activity_id
    ).first()

    if not activity:
        raise HTTPException(status_code=404, detail="ไม่พบกิจกรรมในระบบ")

    activity.is_mission_completed = is_completed
    db.commit()
    db.refresh(activity)

    return activity


@router.delete("/activities/{activity_id}")
def delete_activity(activity_id: int, db: Session = Depends(get_db)):
    """
    ลบกิจกรรม
    """
    activity = db.query(models.ActivityLog).filter(
        models.ActivityLog.id == activity_id
    ).first()

    if not activity:
        raise HTTPException(status_code=404, detail="ไม่พบกิจกรรมในระบบ")

    db.delete(activity)
    db.commit()

    return {"message": "ลบกิจกรรมเรียบร้อยแล้ว"}
