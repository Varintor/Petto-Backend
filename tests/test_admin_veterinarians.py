from types import SimpleNamespace

import pytest

from app import models
from app.config import EnvironmentValidationError, validate_environment
from app.routers import admin_veterinarians


ADMIN_HEADERS = {"X-Admin-Key": "test-admin-key-with-enough-entropy"}


def _staging_environment():
    return {
        "APP_ENV": "staging",
        "DATABASE_URL": "postgresql://postgres.project:password@db.example.com:5432/postgres",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_KEY": "publishable-key",
        "GEMINI_API_KEY": "gemini-key",
        "ENABLE_MOCK_DATA": "false",
    }


def _create_vet(client, *, email="vet@petto.test", license_number="VET-001"):
    return client.post(
        "/api/v1/admin/veterinarians",
        headers=ADMIN_HEADERS,
        json={
            "email": email,
            "name": "Dr. Petto",
            "clinic_name": "Petto Animal Hospital",
            "license_number": license_number,
            "specialty": "General practice",
        },
    )


def test_admin_api_is_unavailable_until_configured(client, monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)

    response = client.get("/api/v1/admin/veterinarians")

    assert response.status_code == 503
    assert response.json()["detail"] == "Veterinarian administration is not configured"


def test_deployed_admin_configuration_requires_strong_key_and_supabase_secret():
    values = _staging_environment()
    values["ADMIN_API_KEY"] = "short"

    with pytest.raises(EnvironmentValidationError) as error:
        validate_environment(values)

    assert "at least 24 characters" in str(error.value)
    assert "SUPABASE_SECRET_KEY is required" in str(error.value)
    assert "VET_INVITE_REDIRECT_URL is required" in str(error.value)


def test_deployed_admin_configuration_accepts_current_supabase_secret_key():
    values = _staging_environment()
    values["ADMIN_API_KEY"] = ADMIN_HEADERS["X-Admin-Key"]
    values["SUPABASE_SECRET_KEY"] = "sb_secret_server-only"
    values["VET_INVITE_REDIRECT_URL"] = "petto://reset-password"

    assert validate_environment(values) == "staging"


def test_admin_api_rejects_an_invalid_credential(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_HEADERS["X-Admin-Key"])

    response = client.get(
        "/api/v1/admin/veterinarians",
        headers={"X-Admin-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_admin_creates_searches_and_prevents_duplicate_veterinarians(
    client, db, monkeypatch
):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_HEADERS["X-Admin-Key"])

    created = _create_vet(client)

    assert created.status_code == 201
    assert created.json()["verification_status"] == "pending"
    assert created.json()["is_accepting_consultations"] is False
    assert created.json()["supabase_uid"] is None

    result = client.get(
        "/api/v1/admin/veterinarians?search=PETTO",
        headers=ADMIN_HEADERS,
    )
    assert result.status_code == 200
    assert [item["email"] for item in result.json()] == ["vet@petto.test"]

    duplicate = _create_vet(
        client,
        email="VET@PETTO.TEST",
        license_number="VET-002",
    )
    assert duplicate.status_code == 409
    assert db.query(models.Veterinarian).count() == 1


def test_admin_approves_and_assigns_a_veterinarian_to_a_provider(
    client, db, monkeypatch
):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_HEADERS["X-Admin-Key"])
    provider = models.VeterinaryProvider(
        name="CMU Animal Hospital",
        provider_type="hospital",
        provider_status="partner",
        consultation_enabled=True,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    veterinarian_id = _create_vet(client).json()["id"]

    blocked = client.put(
        f"/api/v1/admin/veterinarians/{veterinarian_id}/providers/{provider.id}",
        headers=ADMIN_HEADERS,
        json={"accepting_consultations": True},
    )
    assert blocked.status_code == 409

    approved = client.post(
        f"/api/v1/admin/veterinarians/{veterinarian_id}/verification",
        headers=ADMIN_HEADERS,
        json={"verification_status": "approved"},
    )
    assert approved.status_code == 200

    assigned = client.put(
        f"/api/v1/admin/veterinarians/{veterinarian_id}/providers/{provider.id}",
        headers=ADMIN_HEADERS,
        json={"accepting_consultations": True},
    )
    assert assigned.status_code == 200
    assert assigned.json()["provider_ids"] == [provider.id]
    assert assigned.json()["is_accepting_consultations"] is True

    unassigned = client.put(
        f"/api/v1/admin/veterinarians/{veterinarian_id}/providers/{provider.id}",
        headers=ADMIN_HEADERS,
        json={"is_active": False, "accepting_consultations": False},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["provider_ids"] == []
    assert unassigned.json()["is_accepting_consultations"] is False

    reassigned = client.put(
        f"/api/v1/admin/veterinarians/{veterinarian_id}/providers/{provider.id}",
        headers=ADMIN_HEADERS,
        json={"accepting_consultations": True},
    )
    assert reassigned.status_code == 200

    disabled = client.post(
        f"/api/v1/admin/veterinarians/{veterinarian_id}/verification",
        headers=ADMIN_HEADERS,
        json={"verification_status": "disabled"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["is_accepting_consultations"] is False
    link = db.query(models.ProviderVeterinarian).one()
    assert link.accepting_consultations is False


def test_admin_invites_veterinarian_and_links_supabase_uid(
    client, monkeypatch
):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_HEADERS["X-Admin-Key"])
    monkeypatch.setenv(
        "VET_INVITE_REDIRECT_URL",
        "https://petto.test/auth/recovery",
    )
    veterinarian_id = _create_vet(client).json()["id"]
    captured = {}

    class _FakeAdminAuth:
        def invite_user_by_email(self, email, options):
            captured["email"] = email
            captured["options"] = options
            return SimpleNamespace(user=SimpleNamespace(id="uid-invited-vet"))

    fake_client = SimpleNamespace(
        auth=SimpleNamespace(admin=_FakeAdminAuth()),
    )
    monkeypatch.setattr(
        admin_veterinarians,
        "get_supabase_admin_client",
        lambda: fake_client,
    )

    response = client.post(
        f"/api/v1/admin/veterinarians/{veterinarian_id}/invite",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["supabase_uid"] == "uid-invited-vet"
    assert captured == {
        "email": "vet@petto.test",
        "options": {
            "data": {"petto_invited_vet": True, "name": "Dr. Petto"},
            "redirect_to": "https://petto.test/auth/recovery",
        },
    }


def test_invitation_requires_server_side_supabase_admin_configuration(
    client, monkeypatch
):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_HEADERS["X-Admin-Key"])
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("VET_INVITE_REDIRECT_URL", "petto://reset-password")
    veterinarian_id = _create_vet(client).json()["id"]

    response = client.post(
        f"/api/v1/admin/veterinarians/{veterinarian_id}/invite",
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Veterinarian invitations are not configured"
