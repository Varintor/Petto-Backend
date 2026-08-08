# -*- coding: utf-8 -*-
"""Regression tests for the bounded unified health-history timeline."""
from datetime import timedelta

from app import models
from app.utils.time import now_bkk, today_bkk


def test_history_merges_orders_and_limits_rows(auth_client, pet, db):
    now = now_bkk()
    for index in range(5):
        db.add(models.ActivityLog(
            pet_id=pet.id,
            activity_type="walking",
            duration_minutes=10,
            distance_meters=100,
            created_at=now - timedelta(minutes=index),
        ))
    db.add(models.HealthAssessment(
        pet_id=pet.id,
        symptom_description="Routine check",
        risk_level=models.RiskLevel.LOW,
        created_at=now + timedelta(minutes=1),
    ))
    db.commit()

    response = auth_client.get(f"/api/v1/pets/{pet.id}/history?limit=3")

    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert len(entries) == 3
    assert entries[0]["type"] == "assessment"
    assert [entry["timestamp"] for entry in entries] == sorted(
        [entry["timestamp"] for entry in entries], reverse=True
    )


def test_history_applies_type_and_date_filters_in_database(auth_client, pet, db):
    now = now_bkk()
    db.add_all([
        models.ActivityLog(
            pet_id=pet.id, activity_type="walking", duration_minutes=10,
            distance_meters=100, created_at=now,
        ),
        models.ActivityLog(
            pet_id=pet.id, activity_type="walking", duration_minutes=10,
            distance_meters=100, created_at=now - timedelta(days=10),
        ),
        models.HealthAssessment(
            pet_id=pet.id, symptom_description="Excluded by type",
            risk_level=models.RiskLevel.LOW, created_at=now,
        ),
    ])
    db.commit()

    day = today_bkk().isoformat()
    response = auth_client.get(
        f"/api/v1/pets/{pet.id}/history?types=activity&date_from={day}&date_to={day}"
    )

    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["type"] == "activity"
