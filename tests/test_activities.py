# -*- coding: utf-8 -*-
"""UTC-07: Activity Tracking module (auto-complete walk mission, calories)."""
from app import models
from app.utils.time import now_bkk


def _seed_walk_mission(db, pet_id):
    m = models.DailyMission(
        pet_id=pet_id,
        mission_date=now_bkk().date(),
        title="Walk for 15 minutes",
        mission_type="walk",
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def test_qualifying_walk_completes_mission(auth_client, pet, db):
    mission = _seed_walk_mission(db, pet.id)
    r = auth_client.post("/api/v1/activities", json={
        "pet_id": pet.id, "activity_type": "walking",
        "duration_minutes": 20, "is_mission_completed": True,
    })
    assert r.status_code == 200, r.text
    db.refresh(mission)
    assert mission.is_completed is True


def test_calories_auto_calculated(auth_client, pet):
    # MET(walking)=3.0 x weight 10 kg x 0.5 h = 15.0
    r = auth_client.post("/api/v1/activities", json={
        "pet_id": pet.id, "activity_type": "walking", "duration_minutes": 30,
    })
    assert r.status_code == 200, r.text
    assert r.json()["calories_burned"] == 15.0


def test_short_walk_does_not_complete_mission(auth_client, pet, db):
    mission = _seed_walk_mission(db, pet.id)
    r = auth_client.post("/api/v1/activities", json={
        "pet_id": pet.id, "activity_type": "walking",
        "duration_minutes": 10, "is_mission_completed": True,
    })
    assert r.status_code == 200, r.text
    db.refresh(mission)
    assert mission.is_completed is False  # 10 < 15 minutes


def test_activity_requires_existing_pet(auth_client):
    r = auth_client.post("/api/v1/activities", json={
        "pet_id": 9999, "activity_type": "walking", "duration_minutes": 20,
    })
    assert r.status_code == 404
