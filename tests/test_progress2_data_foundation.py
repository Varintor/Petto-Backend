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
    assert body["profile_updated_at"] == update.json()["updated_at"]
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


def test_assigned_vet_reads_only_active_shared_assessment_and_owner_revokes(
    auth_client, pet, approved_vet, db
):
    assessment = models.HealthAssessment(
        pet_id=pet.id,
        symptom_description="Lethargic and not eating",
        status="failed",
        error_code="AI_TIMEOUT",
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    consultation = auth_client.post(
        "/api/v1/consultations",
        json={"pet_id": pet.id, "vet_id": approved_vet.id},
    ).json()
    shared = auth_client.post(
        f"/api/v1/consultations/{consultation['id']}/shared-assessments",
        json={"assessment_id": assessment.id},
    )
    assert shared.status_code == 200, shared.text

    app.dependency_overrides[get_current_actor] = lambda: AuthenticatedActor(
        role="vet", veterinarian=approved_vet
    )
    visible = auth_client.get(
        f"/api/v1/consultations/{consultation['id']}/shared-assessments"
    )
    app.dependency_overrides.pop(get_current_actor, None)
    assert visible.status_code == 200, visible.text
    assert visible.json()[0]["assessment"]["status"] == "failed"
    assert visible.json()[0]["assessment"]["risk_level"] is None
    assert visible.json()[0]["assessment"]["error_code"] == "AI_TIMEOUT"

    revoked = auth_client.delete(
        f"/api/v1/consultations/{consultation['id']}/shared-assessments/{assessment.id}"
    )
    assert revoked.status_code == 204
    assert auth_client.get(
        f"/api/v1/consultations/{consultation['id']}/shared-assessments"
    ).json() == []


def test_provider_directory_exposes_only_available_verified_vets(
    auth_client, approved_vet, db
):
    provider = models.VeterinaryProvider(
        name="CMU Small Animal Hospital",
        provider_type="hospital",
        address="Chiang Mai",
        phone="053-000-000",
        latitude=18.795,
        longitude=98.952,
        provider_status="partner",
        consultation_enabled=True,
    )
    hidden_vet = models.Veterinarian(
        email="hidden-vet@test.com",
        name="Dr. Hidden",
        verification_status="pending",
        is_accepting_consultations=True,
    )
    db.add_all([provider, hidden_vet])
    db.flush()
    db.add_all([
        models.ProviderVeterinarian(
            provider_id=provider.id,
            veterinarian_id=approved_vet.id,
            is_active=True,
            accepting_consultations=True,
        ),
        models.ProviderVeterinarian(
            provider_id=provider.id,
            veterinarian_id=hidden_vet.id,
            is_active=True,
            accepting_consultations=True,
        ),
    ])
    db.commit()

    directory = auth_client.get(
        "/api/v1/veterinary-providers",
        params={"latitude": 18.79, "longitude": 98.95},
    )
    assert directory.status_code == 200, directory.text
    assert directory.json()[0]["distance_km"] is not None

    vets = auth_client.get(
        f"/api/v1/veterinary-providers/{provider.id}/veterinarians"
    )
    assert vets.status_code == 200, vets.text
    assert [item["id"] for item in vets.json()] == [approved_vet.id]


def test_urgent_help_requires_acknowledged_petto_provider(
    auth_client, pet, approved_vet, db
):
    provider = models.VeterinaryProvider(
        name="Petto Partner Hospital",
        provider_type="hospital",
        provider_status="partner",
        consultation_enabled=True,
    )
    db.add(provider)
    db.flush()
    db.add(
        models.ProviderVeterinarian(
            provider_id=provider.id,
            veterinarian_id=approved_vet.id,
            is_active=True,
            accepting_consultations=True,
        )
    )
    db.commit()

    payload = {
        "pet_id": pet.id,
        "vet_id": approved_vet.id,
        "provider_id": provider.id,
        "priority": "urgent",
    }
    missing_ack = auth_client.post("/api/v1/consultations", json=payload)
    assert missing_ack.status_code == 422
    assert missing_ack.json()["detail"] == "Urgent Help disclaimer must be acknowledged"

    urgent = auth_client.post(
        "/api/v1/consultations",
        json={**payload, "urgent_help_acknowledged": True},
    )
    assert urgent.status_code == 200, urgent.text
    assert urgent.json()["priority"] == "urgent"
    assert urgent.json()["subject"] == "Urgent Help"


def test_urgent_help_cannot_target_information_only_provider(
    auth_client, pet, approved_vet, db
):
    provider = models.VeterinaryProvider(
        name="Information Only Hospital",
        provider_type="hospital",
        provider_status="listed",
        consultation_enabled=False,
    )
    db.add(provider)
    db.commit()

    response = auth_client.post(
        "/api/v1/consultations",
        json={
            "pet_id": pet.id,
            "vet_id": approved_vet.id,
            "provider_id": provider.id,
            "priority": "urgent",
            "urgent_help_acknowledged": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Consultation is not available for this provider"


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


def test_reschedule_and_cancel_stay_synchronized_with_calendar(
    auth_client, pet, approved_vet, db
):
    consultation = auth_client.post(
        "/api/v1/consultations",
        json={"pet_id": pet.id, "vet_id": approved_vet.id},
    ).json()
    app.dependency_overrides[get_current_actor] = lambda: AuthenticatedActor(
        role="vet", veterinarian=approved_vet
    )
    starts_at = now_bkk() + timedelta(days=3)
    proposed = auth_client.post(
        f"/api/v1/consultations/{consultation['id']}/appointments",
        json={"starts_at": starts_at.isoformat(), "reason": "Initial follow-up"},
    )
    app.dependency_overrides.pop(get_current_actor, None)
    assert proposed.status_code == 200, proposed.text
    appointment_id = proposed.json()["id"]

    accepted = auth_client.put(
        f"/api/v1/appointments/{appointment_id}/decision",
        json={"decision": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text

    rescheduled_at = now_bkk() + timedelta(days=5)
    app.dependency_overrides[get_current_actor] = lambda: AuthenticatedActor(
        role="vet", veterinarian=approved_vet
    )
    rescheduled = auth_client.put(
        f"/api/v1/appointments/{appointment_id}",
        json={
            "starts_at": rescheduled_at.isoformat(),
            "reason": "Rescheduled follow-up",
        },
    )
    app.dependency_overrides.pop(get_current_actor, None)
    assert rescheduled.status_code == 200, rescheduled.text
    assert rescheduled.json()["status"] == "accepted"
    assert rescheduled.json()["reason"] == "Rescheduled follow-up"

    events = auth_client.get(f"/api/v1/pets/{pet.id}/calendar-events").json()
    assert len(events) == 1
    assert events[0]["appointment_id"] == appointment_id
    assert events[0]["event_date"] == rescheduled_at.date().isoformat()

    cancelled = auth_client.put(f"/api/v1/appointments/{appointment_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert auth_client.get(
        f"/api/v1/pets/{pet.id}/calendar-events"
    ).json() == []


def test_owner_controls_health_card_shared_with_assigned_vet(
    auth_client, pet, approved_vet, db
):
    outsider = models.Veterinarian(
        supabase_uid="uid-outsider-vet",
        email="outsider-vet@test.com",
        name="Dr. Outsider",
        verification_status="approved",
        is_accepting_consultations=True,
    )
    db.add(outsider)
    db.commit()

    consultation = auth_client.post(
        "/api/v1/consultations",
        json={"pet_id": pet.id, "vet_id": approved_vet.id},
    )
    assert consultation.status_code == 200, consultation.text
    consultation_id = consultation.json()["id"]

    shared = auth_client.post(
        f"/api/v1/consultations/{consultation_id}/shared-health-cards"
    )
    assert shared.status_code == 200, shared.text
    shared_id = shared.json()["id"]
    assert shared.json()["snapshot"]["pet_id"] == pet.id

    app.dependency_overrides[get_current_actor] = lambda: AuthenticatedActor(
        role="vet", veterinarian=approved_vet
    )
    assigned_view = auth_client.get(
        f"/api/v1/consultations/{consultation_id}/shared-health-cards"
    )
    assert assigned_view.status_code == 200
    assert [item["id"] for item in assigned_view.json()] == [shared_id]
    vet_share_attempt = auth_client.post(
        f"/api/v1/consultations/{consultation_id}/shared-health-cards"
    )
    assert vet_share_attempt.status_code == 403

    app.dependency_overrides[get_current_actor] = lambda: AuthenticatedActor(
        role="vet", veterinarian=outsider
    )
    assert auth_client.get(
        f"/api/v1/consultations/{consultation_id}/shared-health-cards"
    ).status_code == 404

    app.dependency_overrides.pop(get_current_actor, None)
    revoked = auth_client.delete(
        f"/api/v1/consultations/{consultation_id}/shared-health-cards/{shared_id}"
    )
    assert revoked.status_code == 204
    assert auth_client.get(
        f"/api/v1/consultations/{consultation_id}/shared-health-cards"
    ).json() == []
