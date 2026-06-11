from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
from typing import Dict, Any
from pydantic import BaseModel

from app import models
from app.database import get_db
from app.utils.time import now_bkk, today_bkk

router = APIRouter(
    prefix="/api/v1",
    tags=["Statistics (สถิติ & Dashboard)"]
)


# ==========================================
# Schemas
# ==========================================

class DashboardStatsResponse(BaseModel):
    # Health Score (0-100)
    health_score: int

    # Activity Summary (เดือนนี้)
    activities_this_month: int
    total_duration_minutes: float
    total_distance_meters: float

    # Assessment Summary
    last_assessment: Dict[str, Any] | None
    recent_risk_level: str | None

    # Vaccination Status
    vaccination_status: str  # "up_to_date", "due_soon", "overdue"
    next_vaccination_date: datetime | None

    # Mission Progress
    missions_completed_this_week: int
    mission_streak: int  # ทำติดต่อกันกี่วัน

    class Config:
        from_attributes = True


class HealthScoreBreakdown(BaseModel):
    overall_score: int
    activity_score: int
    health_assessment_score: int
    vaccination_score: int


# ==========================================
# Dashboard Stats Endpoint
# ==========================================

@router.get("/pets/{pet_id}/stats/dashboard", response_model=DashboardStatsResponse)
def get_dashboard_stats(pet_id: int, db: Session = Depends(get_db)):
    """
    ดูสถิติรวมทั้งหมดของสัตว์เลี้ยงตัวหนึ่ง (สำหรับหน้า Dashboard)

    คำนวณ:
    - Health Score (คะแนนสุขภาพรวม 0-100)
    - Activity Summary (กิจกรรมเดือนนี้)
    - Last Assessment (การประเมินล่าสุด)
    - Vaccination Status (สถานะวัคซีน)
    - Mission Progress (ความคืบหน้าภารกิจ)
    """
    # ตรวจสอบว่ามีสัตว์เลี้ยงหรือไม่
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    # ==========================================
    # 1. Health Score Calculation
    # ==========================================
    health_score = _calculate_health_score(pet_id, db)

    # ==========================================
    # 2. Activity Summary (เดือนนี้)
    # ==========================================
    month_start = now_bkk().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    activities = db.query(
        func.count(models.ActivityLog.id).label('count'),
        func.sum(models.ActivityLog.duration_minutes).label('total_duration'),
        func.sum(models.ActivityLog.distance_meters).label('total_distance')
    ).filter(
        models.ActivityLog.pet_id == pet_id,
        models.ActivityLog.created_at >= month_start
    ).first()

    # ==========================================
    # 3. Last Assessment
    # ==========================================
    last_assessment = db.query(models.HealthAssessment).filter(
        models.HealthAssessment.pet_id == pet_id
    ).order_by(models.HealthAssessment.created_at.desc()).first()

    assessment_data = None
    recent_risk = None

    if last_assessment:
        assessment_data = {
            "id": last_assessment.id,
            "risk_level": last_assessment.risk_level.value,
            "created_at": last_assessment.created_at.isoformat(),
            "symptom_description": last_assessment.symptom_description[:100] + "..." if len(last_assessment.symptom_description) > 100 else last_assessment.symptom_description
        }
        recent_risk = last_assessment.risk_level.value

    # ==========================================
    # 4. Vaccination Status
    # ==========================================
    vaccinations = db.query(models.Vaccination).filter(
        models.Vaccination.pet_id == pet_id
    ).order_by(models.Vaccination.next_due_date.desc()).all()

    vaccination_status, next_vac_date = _get_vaccination_status(vaccinations)

    # ==========================================
    # 5. Mission Progress
    # ==========================================
    missions_this_week = db.query(func.count(models.ActivityLog.id)).filter(
        models.ActivityLog.pet_id == pet_id,
        models.ActivityLog.is_mission_completed == True,
        models.ActivityLog.created_at >= now_bkk() - timedelta(days=7)
    ).scalar() or 0

    # คำนวณ Streak (ทำติดต่อกันกี่วัน)
    mission_streak = _calculate_mission_streak(pet_id, db)

    return DashboardStatsResponse(
        health_score=health_score,
        activities_this_month=activities.count or 0,
        total_duration_minutes=float(activities.total_duration or 0),
        total_distance_meters=float(activities.total_distance or 0),
        last_assessment=assessment_data,
        recent_risk_level=recent_risk,
        vaccination_status=vaccination_status,
        next_vaccination_date=next_vac_date,
        missions_completed_this_week=missions_this_week,
        mission_streak=mission_streak
    )


@router.get("/pets/{pet_id}/stats/health-score", response_model=HealthScoreBreakdown)
def get_health_score_breakdown(pet_id: int, db: Session = Depends(get_db)):
    """
    ดู Health Score แบบละเอียด (แยกเป็นส่วนๆ)
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    activity_score = _calculate_activity_score(pet_id, db)
    assessment_score = _calculate_assessment_score(pet_id, db)
    vaccination_score = _calculate_vaccination_score(pet_id, db)

    # Overall Score (เฉลี่ยถ่วง)
    overall_score = int(
        (activity_score * 0.4) +
        (assessment_score * 0.4) +
        (vaccination_score * 0.2)
    )

    return HealthScoreBreakdown(
        overall_score=overall_score,
        activity_score=activity_score,
        health_assessment_score=assessment_score,
        vaccination_score=vaccination_score
    )


@router.get("/pets/{pet_id}/stats/trends")
def get_health_trends(pet_id: int, days: int = 30, db: Session = Depends(get_db)):
    """
    ดู Trend สุขภาพย้อนหลัง X วัน

    ใช้สำหรับกราฟใน Dashboard
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    start_date = now_bkk() - timedelta(days=days)

    # Activity trend (รายวัน)
    activities = db.query(
        func.date(models.ActivityLog.created_at).label('date'),
        func.sum(models.ActivityLog.duration_minutes).label('duration'),
        func.sum(models.ActivityLog.distance_meters).label('distance'),
        func.count(models.ActivityLog.id).label('count')
    ).filter(
        models.ActivityLog.pet_id == pet_id,
        models.ActivityLog.created_at >= start_date
    ).group_by(
        func.date(models.ActivityLog.created_at)
    ).all()

    # Assessment trend
    assessments = db.query(
        func.date(models.HealthAssessment.created_at).label('date'),
        models.HealthAssessment.risk_level
    ).filter(
        models.HealthAssessment.pet_id == pet_id,
        models.HealthAssessment.created_at >= start_date
    ).all()

    return {
        "period_days": days,
        "activity_trend": [
            {
                "date": str(a.date),
                "duration_minutes": float(a.duration or 0),
                "distance_meters": float(a.distance or 0),
                "activities_count": a.count
            }
            for a in activities
        ],
        "assessment_trend": [
            {
                "date": str(a.date),
                "risk_level": a.risk_level.value
            }
            for a in assessments
        ]
    }


# ==========================================
# Helper Functions
# ==========================================

def _calculate_health_score(pet_id: int, db: Session) -> int:
    """คำนวณ Health Score รวม (0-100)"""
    activity_score = _calculate_activity_score(pet_id, db)
    assessment_score = _calculate_assessment_score(pet_id, db)
    vaccination_score = _calculate_vaccination_score(pet_id, db)

    return int(
        (activity_score * 0.4) +
        (assessment_score * 0.4) +
        (vaccination_score * 0.2)
    )


def _calculate_activity_score(pet_id: int, db: Session) -> int:
    """คำนวณคะแนนจากกิจกรรม (0-100)"""
    # ดูกิจกรรม 7 วันล่าสุด
    week_ago = now_bkk() - timedelta(days=7)

    activities = db.query(
        func.sum(models.ActivityLog.duration_minutes).label('total_duration'),
        func.count(models.ActivityLog.id).label('count')
    ).filter(
        models.ActivityLog.pet_id == pet_id,
        models.ActivityLog.created_at >= week_ago
    ).first()

    total_minutes = float(activities.total_duration or 0)
    activity_count = activities.count or 0

    # คะแนนจากจำนวนวันที่ออกกำลังกาย
    active_days = min(activity_count, 7)  # สูงสุด 7 วัน
    base_score = (active_days / 7) * 60  # 0-60 คะแนน

    # โบนัสจากเวลาออกกำลังกาย (เฉลี่ี่อย่างน้อย 30 นาที/วัน)
    if activity_count > 0:
        avg_minutes = total_minutes / activity_count
        if avg_minutes >= 30:
            base_score += 40  # โบนัสเต็ม
        else:
            base_score += (avg_minutes / 30) * 40  # โบนัสตามสัดส่วน

    return min(int(base_score), 100)


def _calculate_assessment_score(pet_id: int, db: Session) -> int:
    """คำนวณคะแนนจากสถานะสุขภาพ (0-100)"""
    # ดูการประเมินล่าสุด
    last_assessment = db.query(models.HealthAssessment).filter(
        models.HealthAssessment.pet_id == pet_id
    ).order_by(models.HealthAssessment.created_at.desc()).first()

    if not last_assessment:
        return 70  # ค่าเริ่มต้น ถ้าไม่เคยประเมิน

    # คะแนนตาม Risk Level
    risk_scores = {
        models.RiskLevel.LOW: 90,
        models.RiskLevel.MODERATE: 60,
        models.RiskLevel.HIGH: 30
    }

    base_score = risk_scores.get(last_assessment.risk_level, 50)

    # โบนัสถ้าประเมินเมื่อเร็วๆ นี้ (ภายใน 7 วัน)
    days_since = (now_bkk() - last_assessment.created_at).days
    if days_since <= 7:
        base_score += 10
    elif days_since <= 30:
        base_score += 5

    return min(base_score, 100)


def _calculate_vaccination_score(pet_id: int, db: Session) -> int:
    """คำนวณคะแนนจากสถานะวัคซีน (0-100)"""
    vaccinations = db.query(models.Vaccination).filter(
        models.Vaccination.pet_id == pet_id
    ).order_by(models.Vaccination.date_administered.desc()).all()

    if not vaccinations:
        return 50  # ค่าเริ่มต้น

    # ตรวจสอบวัคซีนล่าสุด
    last_vac = vaccinations[0]

    if not last_vac.next_due_date:
        return 100  # ไม่มีวันนัดต่อ = เสร็จสิ้นแล้ว

    days_until_due = (last_vac.next_due_date - today_bkk()).days

    if days_until_due < 0:
        return 20  # เกินวันนัดแล้ว
    elif days_until_due <= 7:
        return 60  # ใกล้ถึงวันนัด
    elif days_until_due <= 30:
        return 80   # อีก 1 เดือนถึงวันนัด
    else:
        return 100  # ยังอีกนาน


def _get_vaccination_status(vaccinations: list) -> tuple[str, datetime | None]:
    """ตรวจสอบสถานะวัคซีน"""
    if not vaccinations:
        return "no_records", None

    last_vac = vaccinations[0]

    if not last_vac.next_due_date:
        return "up_to_date", None

    days_until = (last_vac.next_due_date - today_bkk()).days

    if days_until < 0:
        return "overdue", last_vac.next_due_date
    elif days_until <= 7:
        return "due_soon", last_vac.next_due_date
    else:
        return "up_to_date", last_vac.next_due_date


def _calculate_mission_streak(pet_id: int, db: Session) -> int:
    """คำนวณ Streak (ทำติดต่อกันกี่วัน)"""
    streak = 0
    current_date = today_bkk()

    while True:
        # day_start/day_end must be tz-aware to compare with created_at (UTC in DB)
        day_start = datetime.combine(current_date, datetime.min.time(), tzinfo=now_bkk().tzinfo)
        day_end = datetime.combine(current_date, datetime.max.time(), tzinfo=now_bkk().tzinfo)

        activity = db.query(models.ActivityLog).filter(
            models.ActivityLog.pet_id == pet_id,
            models.ActivityLog.is_mission_completed == True,
            models.ActivityLog.created_at >= day_start,
            models.ActivityLog.created_at <= day_end
        ).first()

        if activity:
            streak += 1
            current_date -= timedelta(days=1)
        else:
            break

        # ตรวจสอบไม่ให้วนลูป
        if streak > 365:  # จำกัด 1 ปี
            break

    return streak
