# -*- coding: utf-8 -*-
"""UTC-06: Daily Mission module (seed, complete, uniqueness)."""
from app import models


def test_seed_today_missions(auth_client, pet):
    r = auth_client.post(f"/api/v1/pets/{pet.id}/missions/seed-today")
    assert r.status_code == 200, r.text
    missions = r.json()
    assert len(missions) == 5  # 3 core + 2 bonus
    types = {m["mission_type"] for m in missions}
    assert {"walk", "water", "ai_check"} <= types


def test_seed_today_is_idempotent(auth_client, pet):
    auth_client.post(f"/api/v1/pets/{pet.id}/missions/seed-today")
    r = auth_client.post(f"/api/v1/pets/{pet.id}/missions/seed-today")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 5  # no duplicates


def test_complete_mission(auth_client, pet, db):
    auth_client.post(f"/api/v1/pets/{pet.id}/missions/seed-today")
    mission = db.query(models.DailyMission).filter_by(pet_id=pet.id).first()
    r = auth_client.put(f"/api/v1/missions/{mission.id}/complete")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_completed"] is True
    assert data["completed_at"] is not None


def test_duplicate_mission_conflict(auth_client, pet):
    first = auth_client.post("/api/v1/missions",
                        json={"pet_id": pet.id, "title": "Walk", "mission_type": "walk"})
    assert first.status_code == 200, first.text
    dup = auth_client.post("/api/v1/missions",
                      json={"pet_id": pet.id, "title": "Walk again", "mission_type": "walk"})
    assert dup.status_code == 409
