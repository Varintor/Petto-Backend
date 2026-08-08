# -*- coding: utf-8 -*-
import pytest
from app import models
from app.utils.time import now_bkk

# ITC-05: Idempotent Daily Mission Seeding
# Test ID: mission_seeding_idempotency

def test_mission_seeding_first_call(auth_client, pet, db):
    """ITC-05-TC-01: First seed invocation generates 5 missions"""
    
    response = auth_client.post(f"/api/v1/pets/{pet.id}/missions/seed-today")
    assert response.status_code == 200
    
    # Verify exactly 5 missions were created
    today = now_bkk().date()
    missions = db.query(models.DailyMission).filter(
        models.DailyMission.pet_id == pet.id,
        models.DailyMission.mission_date == today
    ).all()
    
    assert len(missions) == 5
    
    assert len(missions) == 5


def test_mission_seeding_subsequent_calls_idempotent(auth_client, pet, db):
    """ITC-05-TC-02: Subsequent seed calls ignore gracefully"""
    
    # Call 1
    response1 = auth_client.post(f"/api/v1/pets/{pet.id}/missions/seed-today")
    assert response1.status_code == 200
    
    # Call 2
    response2 = auth_client.post(f"/api/v1/pets/{pet.id}/missions/seed-today")
    assert response2.status_code == 200
    
    # Verify exactly 5 missions exist, no duplicates
    today = now_bkk().date()
    missions = db.query(models.DailyMission).filter(
        models.DailyMission.pet_id == pet.id,
        models.DailyMission.mission_date == today
    ).all()
    
    assert len(missions) == 5
