# -*- coding: utf-8 -*-
"""Progress II skeleton tests: Feature 3 (vet consultation + AI assist),
Feature 5 (health history timeline), and multi-device tracking."""
from datetime import date

import pytest

from app import models
from app.utils.time import now_bkk


@pytest.fixture()
def vet(db):
    v = models.Veterinarian(
        email="vet@test.com", name="Dr. Vet", is_online=True,
        verification_status="approved", is_accepting_consultations=True,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@pytest.fixture()
def consultation(auth_client, pet, vet):
    r = auth_client.post("/api/v1/consultations",
                         json={"pet_id": pet.id, "vet_id": vet.id})
    assert r.status_code == 200, r.text
    return r.json()


# ==========================================
# Feature 3: consultation + AI assist
# ==========================================
def test_create_consultation_with_forwarded_assessment(auth_client, pet, vet, db):
    a = models.HealthAssessment(pet_id=pet.id, symptom_description="Ear scratching",
                                risk_level=models.RiskLevel.MODERATE)
    db.add(a)
    db.commit()
    db.refresh(a)

    r = auth_client.post("/api/v1/consultations",
                         json={"pet_id": pet.id, "vet_id": vet.id, "assessment_id": a.id})
    assert r.status_code == 200, r.text
    assert r.json()["assessment_id"] == a.id


def test_consultation_requires_auth(client, pet, vet):
    r = client.post("/api/v1/consultations", json={"pet_id": pet.id, "vet_id": vet.id})
    assert r.status_code in (401, 403)


def test_consultation_response_includes_participant_display_data(
    auth_client, pet, vet
):
    response = auth_client.post(
        "/api/v1/consultations",
        json={"pet_id": pet.id, "vet_id": vet.id},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pet_name"] == pet.name
    assert body["pet_species"] == pet.species
    assert body["owner_name"] == pet.owner.name
    assert body["vet_name"] == vet.name


def test_owner_can_chat_but_cannot_forge_vet(auth_client, consultation):
    cid = consultation["id"]
    ok = auth_client.post(f"/api/v1/consultations/{cid}/messages",
                          json={"sender_type": "user", "content": "Hello doctor"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["sender_type"] == "user"

    forged = auth_client.post(f"/api/v1/consultations/{cid}/messages",
                              json={"sender_type": "vet", "content": "I am a vet, trust me"})
    assert forged.status_code == 403


def test_ai_summary_posts_ai_message(auth_client, consultation, pet, db):
    db.add(models.ActivityLog(pet_id=pet.id, activity_type="walking",
                              duration_minutes=20, distance_meters=1200))
    db.commit()

    cid = consultation["id"]
    r = auth_client.post(f"/api/v1/consultations/{cid}/ai-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sender_type"] == "ai"
    assert "AI BRIEFING" in body["content"]
    assert "not a diagnosis" in body["content"]

    msgs = auth_client.get(f"/api/v1/consultations/{cid}/messages").json()
    assert any(m["sender_type"] == "ai" for m in msgs)


# ==========================================
# Feature 5: unified health history
# ==========================================
def test_history_merges_all_types_newest_first(auth_client, pet, db):
    db.add(models.HealthAssessment(pet_id=pet.id, symptom_description="Lethargic",
                                   risk_level=models.RiskLevel.LOW))
    db.add(models.ActivityLog(pet_id=pet.id, activity_type="walking",
                              duration_minutes=20, distance_meters=1000))
    db.add(models.Vaccination(pet_id=pet.id, vaccine_name="Rabies",
                              date_administered=date(2026, 6, 1)))
    db.add(models.DailyMission(pet_id=pet.id, mission_date=now_bkk().date(),
                               title="Walk for 15 minutes", mission_type="walk",
                               is_completed=True, completed_at=now_bkk()))
    db.commit()

    r = auth_client.get(f"/api/v1/pets/{pet.id}/history")
    assert r.status_code == 200, r.text
    entries = r.json()["entries"]
    assert {e["type"] for e in entries} == {"assessment", "activity", "vaccination", "mission"}
    stamps = [e["timestamp"] for e in entries]
    assert stamps == sorted(stamps, reverse=True)


def test_history_type_filter(auth_client, pet, db):
    db.add(models.HealthAssessment(pet_id=pet.id, symptom_description="x"))
    db.add(models.Vaccination(pet_id=pet.id, vaccine_name="Rabies",
                              date_administered=date(2026, 6, 1)))
    db.commit()

    r = auth_client.get(f"/api/v1/pets/{pet.id}/history?types=vaccination")
    assert r.status_code == 200
    assert all(e["type"] == "vaccination" for e in r.json()["entries"])
    assert len(r.json()["entries"]) == 1


# ==========================================
# Multi-device tracking (Mode B skeleton)
# ==========================================
def test_pair_list_unpair_device(auth_client, pet):
    r = auth_client.post(f"/api/v1/pets/{pet.id}/devices",
                         json={"name": "Buddy collar", "identifier": "AA:BB:CC:01"})
    assert r.status_code == 200, r.text
    device = r.json()
    assert device["device_type"] == "ble_collar"

    dup = auth_client.post(f"/api/v1/pets/{pet.id}/devices",
                           json={"name": "Clone", "identifier": "AA:BB:CC:01"})
    assert dup.status_code == 409

    listed = auth_client.get(f"/api/v1/pets/{pet.id}/devices").json()
    assert len(listed) == 1

    assert auth_client.delete(f"/api/v1/devices/{device['id']}").status_code == 200
    assert auth_client.get(f"/api/v1/pets/{pet.id}/devices").json() == []


def test_telemetry_updates_position_and_logs_session(auth_client, pet, db):
    device = auth_client.post(f"/api/v1/pets/{pet.id}/devices",
                              json={"name": "Collar", "identifier": "AA:BB:CC:02"}).json()

    r = auth_client.post(f"/api/v1/devices/{device['id']}/telemetry", json={
        "samples": [
            {"lat": 18.7883, "lng": 98.9853, "speed_kmh": 4.0},
            {"lat": 18.7890, "lng": 98.9860, "speed_kmh": 5.0},
        ],
        "battery_percent": 76,
        "session_duration_minutes": 18,
        "session_distance_meters": 1100,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["activity_logged"] is True
    assert body["device"]["last_lat"] == 18.7890
    assert body["device"]["battery_percent"] == 76

    log = db.query(models.ActivityLog).filter_by(pet_id=pet.id).first()
    assert log is not None and log.source == models.ActivitySource.DEVICE


def test_telemetry_flags_abnormal_speed(auth_client, pet):
    device = auth_client.post(f"/api/v1/pets/{pet.id}/devices",
                              json={"name": "Collar", "identifier": "AA:BB:CC:03"}).json()
    r = auth_client.post(f"/api/v1/devices/{device['id']}/telemetry", json={
        "samples": [{"lat": 18.78, "lng": 98.98, "speed_kmh": 60.0}],
    })
    assert r.status_code == 200
    kinds = [a["kind"] for a in r.json()["anomalies"]]
    assert "abnormal_speed" in kinds
