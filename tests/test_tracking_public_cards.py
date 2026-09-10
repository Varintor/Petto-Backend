from uuid import uuid4
from app import models
from app.utils.time import now_bkk


def _device(auth_client, pet, suffix="x"):
    return auth_client.post(f"/api/v1/pets/{pet.id}/devices", json={"name": "Demo", "identifier": f"demo-{suffix}"}).json()


def test_alert_persists_deduplicates_and_acknowledges(auth_client, pet, db):
    device = _device(auth_client, pet, "alerts")
    payload = {"samples": [{"lat": 1, "lng": 1, "speed_kmh": 50}, {"lat": 1.001, "lng": 1.001, "speed_kmh": 51}, {"lat": 1.002, "lng": 1.002, "speed_kmh": 52}], "battery_percent": 10}
    assert auth_client.post(f"/api/v1/devices/{device['id']}/telemetry", json=payload).status_code == 200
    assert auth_client.post(f"/api/v1/devices/{device['id']}/telemetry", json=payload).status_code == 200
    alerts = auth_client.get(f"/api/v1/pets/{pet.id}/device-alerts?active_only=true").json()
    assert {a["alert_type"] for a in alerts} == {"sustained_high_speed", "low_battery"}
    response = auth_client.post(f"/api/v1/device-alerts/{alerts[0]['id']}/acknowledge")
    assert response.status_code == 200 and response.json()["acknowledged_at"]


def test_device_session_is_idempotent_and_completes_walk(auth_client, pet, db):
    device = _device(auth_client, pet, "session")
    db.add(models.DailyMission(pet_id=pet.id, mission_date=now_bkk().date(), title="Walk", mission_type="walk")); db.commit()
    sid = str(uuid4()); payload = {"samples": [{"lat": 1, "lng": 1}], "session_id": sid, "session_duration_minutes": 15}
    first = auth_client.post(f"/api/v1/devices/{device['id']}/telemetry", json=payload).json()
    second = auth_client.post(f"/api/v1/devices/{device['id']}/telemetry", json=payload).json()
    assert first["activity_logged"] is True and second["activity_logged"] is False
    assert db.query(models.ActivityLog).count() == 1
    assert db.query(models.DailyMission).first().is_completed is True


def test_public_card_allowlist_rotate_revoke(auth_client, pet, db):
    db.add(models.PetHealthProfile(pet_id=pet.id, allergies=["pollen"], chronic_conditions=["private"], current_medications=[])); db.commit()
    created = auth_client.put(f"/api/v1/pets/{pet.id}/public-card", json={"visible_fields": ["name", "allergies"]}).json()
    token = created["token"]
    public = auth_client.get(f"/api/v1/public/pets/{token}")
    assert public.status_code == 200 and public.json() == {"name": pet.name, "allergies": ["pollen"]}
    rotated = auth_client.post(f"/api/v1/pets/{pet.id}/public-card/rotate").json()["token"]
    assert auth_client.get(f"/api/v1/public/pets/{token}").status_code == 404
    assert auth_client.get(f"/api/v1/public/pets/{rotated}").status_code == 200
    auth_client.post(f"/api/v1/pets/{pet.id}/public-card/revoke")
    assert auth_client.get(f"/api/v1/public/pets/{rotated}").status_code == 404
