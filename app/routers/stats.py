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
    tags=["Statistics"]
)


# ==========================================
# Schemas
# ==========================================

class DashboardStatsResponse(BaseModel):
    health_score: int
    activities_this_month: int
    total_duration_minutes: float
    total_distance_meters: float
    last_assessment: Dict[str, Any] | None
    recent_risk_level: str | None
    vaccination_status: str  # "up_to_date", "due_soon", "overdue"
    next_vaccination_date: datetime | None
    missions_completed_this_week: int
    mission_streak: int

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
    """Aggregated dashboard statistics for a pet."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    health_score = _calculate_health_score(pet_id, db)

    month_start = now_bkk().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    activities = db.query(
        func.count(models.ActivityLog.id).label('count'),
        func.sum(models.ActivityLog.duration_minutes).label('total_duration'),
        func.sum(models.ActivityLog.distance_meters).label('total_distance')
    ).filter(
        models.ActivityLog.pet_id == pet_id,
        models.ActivityLog.created_at >= month_start
    ).first()

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

    vaccinations = db.query(models.Vaccination).filter(
        models.Vaccination.pet_id == pet_id
    ).order_by(models.Vaccination.next_due_date.desc()).all()

    vaccination_status, next_vac_date = _get_vaccination_status(vaccinations)

    missions_this_week = db.query(func.count(models.ActivityLog.id)).filter(
        models.ActivityLog.pet_id == pet_id,
        models.ActivityLog.is_mission_completed == True,
        models.ActivityLog.created_at >= now_bkk() - timedelta(days=7)
    ).scalar() or 0

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
    """Health score breakdown by category."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    activity_score = _calculate_activity_score(pet_id, db)
    assessment_score = _calculate_assessment_score(pet_id, db)
    vaccination_score = _calculate_vaccination_score(pet_id, db)

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
    """Health trends over the last N days (for dashboard charts)."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    start_date = now_bkk() - timedelta(days=days)

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
    activity_score = _calculate_activity_score(pet_id, db)
    assessment_score = _calculate_assessment_score(pet_id, db)
    vaccination_score = _calculate_vaccination_score(pet_id, db)

    return int(
        (activity_score * 0.4) +
        (assessment_score * 0.4) +
        (vaccination_score * 0.2)
    )


def _calculate_activity_score(pet_id: int, db: Session) -> int:
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

    active_days = min(activity_count, 7)
    base_score = (active_days / 7) * 60

    if activity_count > 0:
        avg_minutes = total_minutes / activity_count
        if avg_minutes >= 30:
            base_score += 40
        else:
            base_score += (avg_minutes / 30) * 40

    return min(int(base_score), 100)


def _calculate_assessment_score(pet_id: int, db: Session) -> int:
    last_assessment = db.query(models.HealthAssessment).filter(
        models.HealthAssessment.pet_id == pet_id
    ).order_by(models.HealthAssessment.created_at.desc()).first()

    if not last_assessment:
        return 70

    risk_scores = {
        models.RiskLevel.LOW: 90,
        models.RiskLevel.MODERATE: 60,
        models.RiskLevel.HIGH: 30
    }

    base_score = risk_scores.get(last_assessment.risk_level, 50)

    days_since = (now_bkk() - last_assessment.created_at).days
    if days_since <= 7:
        base_score += 10
    elif days_since <= 30:
        base_score += 5

    return min(base_score, 100)


def _calculate_vaccination_score(pet_id: int, db: Session) -> int:
    vaccinations = db.query(models.Vaccination).filter(
        models.Vaccination.pet_id == pet_id
    ).order_by(models.Vaccination.date_administered.desc()).all()

    if not vaccinations:
        return 50

    last_vac = vaccinations[0]

    if not last_vac.next_due_date:
        return 100

    days_until_due = (last_vac.next_due_date - today_bkk()).days

    if days_until_due < 0:
        return 20
    elif days_until_due <= 7:
        return 60
    elif days_until_due <= 30:
        return 80
    else:
        return 100


def _get_vaccination_status(vaccinations: list) -> tuple[str, datetime | None]:
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
    streak = 0
    current_date = today_bkk()

    while True:
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

        if streak > 365:
            break

    return streak
