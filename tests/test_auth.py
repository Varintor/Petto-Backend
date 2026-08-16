# -*- coding: utf-8 -*-
"""UTC-01 / UTC-02: Authentication module (register, login)."""
from fastapi import HTTPException
from supabase_auth.errors import AuthApiError

from app import models
from app.auth import request_password_reset


class _FakeAuthResp:
    """Mimics the Supabase auth response (.user.id, .session.access_token)."""
    def __init__(self, uid="uid-new", token="access-token-123", metadata=None):
        self.user = type("U", (), {"id": uid, "user_metadata": metadata or {}})()
        self.session = type("S", (), {
            "access_token": token,
            "refresh_token": "refresh-token-123",
            "expires_at": 1_800_000_000,
        })()


# ---- UTC-01: register ----
def test_register_success(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.register_user", lambda email, pw: _FakeAuthResp())
    r = client.post("/api/v1/auth/register",
                    json={"email": "new@test.com", "password": "Password123!", "name": "Test User"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"]["email"] == "new@test.com"
    assert data["access_token"] == "access-token-123"
    assert data["refresh_token"] == "refresh-token-123"


def test_register_duplicate_email(client, db, monkeypatch):
    db.add(models.User(email="exists@test.com", name="X", supabase_uid="u-1"))
    db.commit()

    def _should_not_call(*a, **k):
        raise AssertionError("register_user must not be called on duplicate")
    monkeypatch.setattr("app.routers.auth.register_user", _should_not_call)

    r = client.post("/api/v1/auth/register",
                    json={"email": "exists@test.com", "password": "Password456!", "name": "Other"})
    assert r.status_code == 409
    assert r.json()["detail"] == "Email already registered"


def test_forgot_password_requests_recovery_without_revealing_account(client, monkeypatch):
    requested = []
    monkeypatch.setattr(
        "app.routers.auth.request_password_reset",
        lambda email, redirect_to=None: requested.append((email, redirect_to)),
    )

    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "Owner@Test.com ", "redirect_to": "petto://reset-password"},
    )

    assert response.status_code == 200
    assert requested == [("owner@test.com", "petto://reset-password")]
    assert response.json()["message"] == (
        "If an account exists for this email, a reset link has been sent."
    )


def test_forgot_password_rejects_invalid_email(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.auth.request_password_reset",
        lambda email, redirect_to=None: (_ for _ in ()).throw(AssertionError("must not send")),
    )
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "not-an-email"},
    )
    assert response.status_code == 422


def test_forgot_password_rejects_untrusted_redirect(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.auth.request_password_reset",
        lambda email, redirect_to=None: (_ for _ in ()).throw(AssertionError("must not send")),
    )
    response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "owner@test.com", "redirect_to": "https://attacker.test/reset"},
    )
    assert response.status_code == 422


def test_password_reset_hides_provider_account_disclosure_errors(monkeypatch):
    fake_auth = type(
        "FakeAuth",
        (),
        {
            "reset_password_for_email": lambda self, email, options=None: (_ for _ in ()).throw(
                AuthApiError("invalid address", 400, "email_address_invalid")
            )
        },
    )()
    monkeypatch.setattr("app.auth.supabase", type("FakeClient", (), {"auth": fake_auth})())

    assert request_password_reset("reserved@example.com") is None


def test_password_reset_reports_provider_outage(monkeypatch):
    fake_auth = type(
        "FakeAuth",
        (),
        {
            "reset_password_for_email": lambda self, email, options=None: (_ for _ in ()).throw(
                AuthApiError("mail service unavailable", 500, "unexpected_failure")
            )
        },
    )()
    monkeypatch.setattr("app.auth.supabase", type("FakeClient", (), {"auth": fake_auth})())

    try:
        request_password_reset("owner@petto.test")
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("provider outages must remain observable")


# ---- UTC-02: login ----
def test_login_success(client, db, monkeypatch):
    db.add(models.User(email="user@test.com", name="U", supabase_uid="uid-1"))
    db.commit()
    monkeypatch.setattr("app.routers.auth.login_user",
                        lambda e, p: _FakeAuthResp(uid="uid-1", token="login-tok"))
    r = client.post("/api/v1/auth/login",
                    json={"email": "user@test.com", "password": "Password123!"})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"] == "login-tok"
    assert r.json()["user"]["email"] == "user@test.com"


def test_login_invalid_credentials(client, monkeypatch):
    def _boom(e, p):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    monkeypatch.setattr("app.routers.auth.login_user", _boom)
    r = client.post("/api/v1/auth/login",
                    json={"email": "user@test.com", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


def test_login_approved_veterinarian_returns_veterinarian_role(client, db, monkeypatch):
    db.add(models.Veterinarian(
        email="doctor@petto.test",
        name="Dr. Petto",
        supabase_uid="uid-vet",
        verification_status="approved",
    ))
    db.commit()
    monkeypatch.setattr(
        "app.routers.auth.login_user",
        lambda e, p: _FakeAuthResp(uid="uid-vet", token="vet-token"),
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "doctor@petto.test", "password": "Password123!"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_token"] == "vet-token"
    assert response.json()["user"]["role"] == "veterinarian"


def test_login_rejects_unapproved_veterinarian(client, db, monkeypatch):
    db.add(models.Veterinarian(
        email="pending@petto.test",
        name="Dr. Pending",
        supabase_uid="uid-vet-pending",
        verification_status="pending",
    ))
    db.commit()
    monkeypatch.setattr(
        "app.routers.auth.login_user",
        lambda e, p: _FakeAuthResp(uid="uid-vet-pending", token="vet-token"),
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "pending@petto.test", "password": "Password123!"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Veterinarian account is not approved"


def test_login_links_legacy_veterinarian_email_to_supabase_uid(client, db, monkeypatch):
    veterinarian = models.Veterinarian(
        email="legacy-vet@petto.test",
        name="Dr. Legacy",
        supabase_uid=None,
        verification_status="approved",
    )
    db.add(veterinarian)
    db.commit()
    monkeypatch.setattr(
        "app.routers.auth.login_user",
        lambda e, p: _FakeAuthResp(uid="uid-linked-vet", token="vet-token"),
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "legacy-vet@petto.test", "password": "Password123!"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "veterinarian"
    db.refresh(veterinarian)
    assert veterinarian.supabase_uid == "uid-linked-vet"
