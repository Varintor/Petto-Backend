# -*- coding: utf-8 -*-
import pytest
from datetime import datetime, timedelta
from app import models
from app.utils.time import now_bkk, today_bkk

# ITC-06: Dashboard Statistics Score Aggregation
# Test ID: dashboard_health_score_aggregation

def test_dashboard_perfect_record(auth_client, pet, db, monkeypatch):
    """ITC-06-TC-01: Perfect record aggregation results in high score"""
    
    # SQLite drops timezone info, causing TypeError when stats.py compares it to offset-aware now_bkk()
    monkeypatch.setattr("app.routers.stats.now_bkk", lambda: datetime.now())
    
    # 1. Add consistent activity
    for i in range(5):
        activity = models.ActivityLog(
            pet_id=pet.id,
            activity_type="walking",
            duration_minutes=30.0,
            distance_meters=1500.0,
            created_at=now_bkk() - timedelta(days=i),
            is_mission_completed=True
        )
        db.add(activity)
    
    # 2. Add safe AI assessment
    assessment = models.HealthAssessment(
        pet_id=pet.id,
        symptom_description="Normal checkup",
        risk_level=models.RiskLevel.LOW,
        created_at=now_bkk() - timedelta(days=1)
    )
    db.add(assessment)
    
    # 3. Add up-to-date vaccine
    vaccine = models.Vaccination(
        pet_id=pet.id,
        vaccine_name="Rabies",
        date_administered=today_bkk() - timedelta(days=30),
        next_due_date=today_bkk() + timedelta(days=335)
    )
    db.add(vaccine)
    db.commit()
    
    response = auth_client.get(f"/api/v1/pets/{pet.id}/stats/dashboard")
    assert response.status_code == 200
    
    data = response.json()
    assert data["health_score"] >= 90
    assert data["vaccination_status"] == "up_to_date"


def test_dashboard_missing_vaccinations(auth_client, db, user, monkeypatch):
    """ITC-06-TC-02: Missing vaccinations decreases score"""
    
    # SQLite drops timezone info, causing TypeError when stats.py compares it to offset-aware now_bkk()
    monkeypatch.setattr("app.routers.stats.now_bkk", lambda: datetime.now())
    
    # Create a second pet for this test
    pet2 = models.Pet(user_id=user.id, name="Pet 2", species="Cat")
    db.add(pet2)
    db.commit()
    db.refresh(pet2)
    
    # Add consistent activity
    for i in range(5):
        activity = models.ActivityLog(
            pet_id=pet2.id,
            activity_type="walking",
            duration_minutes=30.0,
            distance_meters=1500.0,
            created_at=now_bkk() - timedelta(days=i),
            is_mission_completed=True
        )
        db.add(activity)
    
    # Add safe AI assessment
    assessment = models.HealthAssessment(
        pet_id=pet2.id,
        symptom_description="Normal checkup",
        risk_level=models.RiskLevel.LOW,
        created_at=now_bkk() - timedelta(days=1)
    )
    db.add(assessment)
    
    # Add OVERDUE vaccine
    vaccine = models.Vaccination(
        pet_id=pet2.id,
        vaccine_name="Feline Leukemia",
        date_administered=today_bkk() - timedelta(days=400),
        next_due_date=today_bkk() - timedelta(days=35) # Overdue
    )
    db.add(vaccine)
    db.commit()
    
    response = auth_client.get(f"/api/v1/pets/{pet2.id}/stats/dashboard")
    assert response.status_code == 200
    
    data = response.json()
    # Perfect score would be >90, but due to overdue vaccine (20% weight), it should be heavily penalized
    assert data["health_score"] < 90
    assert data["vaccination_status"] == "overdue"
