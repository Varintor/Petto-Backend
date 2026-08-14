from datetime import date, timedelta

import pytest

from app import models
from app.auth import AuthenticatedActor, get_current_actor
from app.main import app
from app.utils.time import now_bkk


@pytest.fixture()
def approved_vet(db):
    vet = models.Veterinarian(
        supabase_uid="uid-vet",
        email="approved-vet@test.com",
        name="Dr. Approved",
        verification_status="approved",
        is_accepting_consultations=True,
    )
    db.add(vet)
    db.commit()
    db.refresh(vet)
    return vet


def test_calendar_event_crud_is_backend_persisted(auth_client, pet):
    created = auth_client.post(
        f"/api/v1/pets/{pet.id}/calendar-events",
        json={
            "title": "Heartworm medicine",
            "event_type": "medication",
            "event_date": "2026-08-20",
            "starts_at": "2026-08-20T09:00:00+07:00",
            "reminder_minutes": 30,
        },
    )
    assert created.status_code == 200, created.text
    event_id = created.json()["id"]

    listed = auth_client.get(f"/api/v1/pets/{pet.id}/calendar-events")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [event_id]

    updated = auth_client.patch(
        f"/api/v1/calendar-events/{event_id}", json={"is_completed": True}
    )
    assert updated.status_code == 200
    assert updated.json()["is_completed"] is True

    assert auth_client.delete(f"/api/v1/calendar-events/{event_id}").status_code == 204


def test_completed_mission_unlocks_persistent_wardrobe_item(auth_client, pet, db):
    mission = models.DailyMission(
        pet_id=pet.id,
        mission_date=date(2026, 8, 11),
        title="Brush fur",
        mission_type="grooming",
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)

    assert auth_client.put(f"/api/v1/missions/{mission.id}/complete").status_code == 200
    items = auth_client.get(f"/api/v1/pets/{pet.id}/wardrobe-items").json()
    assert len(items) == 1
    assert items[0]["accessory_id"] == "acc_brush"

    equipped = auth_client.put(
        f"/api/v1/pets/{pet.id}/wardrobe-items/{items[0]['accessory_id']}/equip"
    )
    assert equipped.status_code == 200
    assert equipped.json()["equipped_at"] is not None


def test_health_card_combines_profile_and_latest_records(auth_client, pet, db):
    update = auth_client.put(
        f"/api/v1/pets/{pet.id}/health-profile",
        json={
            "allergies": ["Chicken"],
            "chronic_conditions": ["Atopy"],
            "current_medications": ["Cetirizine"],
            "notes": "Avoid chicken treats",
        },
    )
    assert update.status_code == 200, update.text
    db.add(models.HealthAssessment(
        pet_id=pet.id,
        symptom_description="Itchy skin",
        risk_level=models.RiskLevel.MODERATE,
    ))
    db.add(models.Vaccination(
        pet_id=pet.id,
        vaccine_name="Rabies",
        date_administered=date(2026, 7, 1),
    ))
    db.commit()

    card = auth_client.get(f"/api/v1/pets/{pet.id}/health-card")
    assert card.status_code == 200, card.text
    body = card.json()
    assert body["name"] == pet.name
    assert body["allergies"] == ["Chicken"]
    assert body["latest_assessment"]["risk_level"] == "Moderate Risk"
    assert body["latest_vaccination"]["title"] == "Vaccination: Rabies"


def test_only_approved_accepting_vet_can_be_consulted(auth_client, pet, db):
    pending = models.Veterinarian(
        email="pending@test.com", name="Dr. Pending", verification_status="pending"
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    response = auth_client.post(
        "/api/v1/consultations", json={"pet_id": pet.id, "vet_id": pending.id}
    )
    assert response.status_code == 404


def test_vet_proposes_and_owner_accepts_appointment_into_calendar(
    auth_client, pet, approved_vet, db
):
    consultation = auth_client.post(
        "/api/v1/consultations",
        json={"pet_id": pet.id, "vet_id": approved_vet.id},
    )
    assert consultation.status_code == 200, consultation.text
    consultation_id = consultation.json()["id"]

    app.dependency_overrides[get_current_actor] = lambda: AuthenticatedActor(
        role="vet", veterinarian=approved_vet
    )
    past = auth_client.post(
        f"/api/v1/consultations/{consultation_id}/appointments",
        json={"starts_at": (now_bkk() - timedelta(minutes=1)).isoformat()},
    )
    assert past.status_code == 422
    starts_at = now_bkk() + timedelta(days=3)
    proposed = auth_client.post(
        f"/api/v1/consultations/{consultation_id}/appointments",
        json={"starts_at": starts_at.isoformat(), "reason": "Skin follow-up"},
    )
    app.dependency_overrides.pop(get_current_actor, None)
    assert proposed.status_code == 200, proposed.text

    listed = auth_client.get(
        f"/api/v1/consultations/{consultation_id}/appointments"
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [proposed.json()["id"]]
    assert listed.json()[0]["status"] == "proposed"

    accepted = auth_client.put(
        f"/api/v1/appointments/{proposed.json()['id']}/decision",
        json={"decision": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    events = auth_client.get(f"/api/v1/pets/{pet.id}/calendar-events").json()
    assert len(events) == 1
    assert events[0]["appointment_id"] == proposed.json()["id"]

    answered = auth_client.get(
        f"/api/v1/consultations/{consultation_id}/appointments"
    ).json()
    assert answered[0]["status"] == "accepted"
