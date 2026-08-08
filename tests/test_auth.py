# -*- coding: utf-8 -*-
"""UTC-01 / UTC-02: Authentication module (register, login)."""
from fastapi import HTTPException
from app import models


class _FakeAuthResp:
    """Mimics the Supabase auth response (.user.id, .session.access_token)."""
    def __init__(self, uid="uid-new", token="access-token-123", metadata=None):
        self.user = type("U", (), {"id": uid, "user_metadata": metadata or {}})()
        self.session = type("S", (), {"access_token": token})()


# ---- UTC-01: register ----
def test_register_success(client, monkeypatch):
    monkeypatch.setattr("app.routers.auth.register_user", lambda email, pw: _FakeAuthResp())
    r = client.post("/api/v1/auth/register",
                    json={"email": "new@test.com", "password": "Password123!", "name": "Test User"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"]["email"] == "new@test.com"
    assert data["access_token"] == "access-token-123"


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
