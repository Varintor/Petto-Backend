# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch
from app import models
from app.utils.time import now_bkk

# ITC-04: Walk Activity & Daily Mission Transactional Sync
# Test ID: walk_activity_mission_sync

@pytest.fixture
def walk_mission(db, pet):
    """Seed an incomplete walk mission for today."""
    today = now_bkk().date()
    mission = models.DailyMission(
        pet_id=pet.id,
        mission_date=today,
        mission_type="walk",
        title="Walk 15 mins",
        is_completed=False
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


def test_activity_completes_mission(auth_client, pet, walk_mission, db):
    """ITC-04-TC-01: Qualifying walk updates mission status"""
    
    activity_data = {
        "pet_id": pet.id,
        "activity_type": "walking",
        "duration_minutes": 20.0,
        "is_mission_completed": True
    }
    
    response = auth_client.post("/api/v1/activities", json=activity_data)
    assert response.status_code == 200
    
    # Verify Activity saved
    data = response.json()
    assert data["duration_minutes"] == 20.0
    
    # Verify Mission updated
    db.refresh(walk_mission)
    assert walk_mission.is_completed is True
    assert walk_mission.completed_at is not None


def test_activity_insufficient_duration(auth_client, pet, walk_mission, db):
    """ITC-04-TC-02: Insufficient duration does not trigger completion"""
    
    activity_data = {
        "pet_id": pet.id,
        "activity_type": "walking",
        "duration_minutes": 10.0,
        "is_mission_completed": True
    }
    
    response = auth_client.post("/api/v1/activities", json=activity_data)
    assert response.status_code == 200
    
    # Verify Mission NOT updated
    db.refresh(walk_mission)
    assert walk_mission.is_completed is False


def test_activity_transactional_rollback(auth_client, pet, walk_mission, db, monkeypatch):
    """ITC-04-TC-03: Transactional Rollback on Mission Update Error"""
    
    # Mock _complete_walk_mission to throw an exception simulating a DB error during update
    def mock_complete(*args, **kwargs):
        raise Exception("Simulated Database Error")
    
    monkeypatch.setattr("app.routers.activities._complete_walk_mission", mock_complete)
    
    activity_data = {
        "pet_id": pet.id,
        "activity_type": "walking",
        "duration_minutes": 25.0,
        "is_mission_completed": True
    }
    
    # It should raise HTTP 500 or just error out
    with pytest.raises(Exception, match="Simulated Database Error"):
        auth_client.post("/api/v1/activities", json=activity_data)
    
    # SQLite in tests with SQLAlchemy autocommit=False might not automatically rollback 
    # unless we explicitly catch and rollback in the route, but in tests, an unhandled exception 
    # rolls back the transaction when the session closes/fails.
    db.rollback()
    
    # Verify Activity was NOT saved because the transaction aborted
    activities = db.query(models.ActivityLog).filter(models.ActivityLog.pet_id == pet.id).all()
    assert len(activities) == 0
    
    # Verify Mission NOT updated
    db.refresh(walk_mission)
    assert walk_mission.is_completed is False
