# -*- coding: utf-8 -*-
"""UTC-08: Statistics module (dashboard aggregation, health score range)."""
from datetime import timedelta

from app import models
from app.utils.time import now_bkk, today_bkk


def test_dashboard_aggregates_activities(auth_client, pet, db):
    for dur in (20, 30):
        db.add(models.ActivityLog(
            pet_id=pet.id, activity_type="walking",
            duration_minutes=dur, distance_meters=1000,
            created_at=now_bkk(),
        ))
    db.commit()

    r = auth_client.get(f"/api/v1/pets/{pet.id}/stats/dashboard")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["activities_this_month"] == 2
    assert data["total_duration_minutes"] == 50
    assert 0 <= data["health_score"] <= 100


def test_health_score_within_range(auth_client, pet):
    r = auth_client.get(f"/api/v1/pets/{pet.id}/stats/health-score")
    assert r.status_code == 200, r.text
    assert 0 <= r.json()["overall_score"] <= 100


def test_activity_score_counts_distinct_days(auth_client, pet, db):
    for index in range(7):
        db.add(models.ActivityLog(
            pet_id=pet.id,
            activity_type="walking",
            duration_minutes=30,
            distance_meters=500,
            created_at=now_bkk() - timedelta(minutes=index),
        ))
    db.commit()

    response = auth_client.get(f"/api/v1/pets/{pet.id}/stats/health-score")

    assert response.status_code == 200, response.text
    assert response.json()["activity_score"] == 48


def test_dashboard_uses_earliest_current_vaccination_due_date(auth_client, pet, db):
    db.add_all([
        models.Vaccination(
            pet_id=pet.id,
            vaccine_name="Rabies",
            date_administered=today_bkk() - timedelta(days=400),
            next_due_date=today_bkk() - timedelta(days=35),
        ),
        models.Vaccination(
            pet_id=pet.id,
            vaccine_name="Distemper",
            date_administered=today_bkk(),
            next_due_date=today_bkk() + timedelta(days=365),
        ),
    ])
    db.commit()

    response = auth_client.get(f"/api/v1/pets/{pet.id}/stats/dashboard")

    assert response.status_code == 200, response.text
    assert response.json()["vaccination_status"] == "overdue"


def test_mission_streak_uses_one_set_of_completed_dates(auth_client, pet, db):
    today = today_bkk()
    now = now_bkk()
    for offset in (0, 1, 2, 4):
        db.add(models.DailyMission(
            pet_id=pet.id,
            mission_date=today - timedelta(days=offset),
            mission_type="walk",
            title="Daily walk",
            is_completed=True,
            completed_at=now - timedelta(days=offset),
        ))
    db.commit()

    response = auth_client.get(f"/api/v1/pets/{pet.id}/stats/dashboard")

    assert response.status_code == 200, response.text
    assert response.json()["mission_streak"] == 3
    assert response.json()["missions_completed_this_week"] == 4
