# -*- coding: utf-8 -*-
"""End-to-end flow: register -> create pet using the issued token.

Exercises the full chain that the Flutter onboarding screen runs eagerly:
  POST /api/v1/auth/register  ->  POST /api/v1/pets (Bearer <token>)

Supabase is stubbed at module level (app.auth) so get_current_user can
resolve the bearer token back to the just-registered user.
"""
from app import models, auth as auth_module
from app.routers import auth as auth_router


class _FakeAuthResp:
    def __init__(self, uid, token, metadata=None):
        self.user = type("U", (), {"id": uid, "user_metadata": metadata or {}})()
        self.session = type("S", (), {"access_token": token}) () if token else None


class _StubSupabaseAuth:
    """Minimal stand-in for supabase.auth used by get_current_user."""
    def __init__(self):
        self._token_to_uid: dict[str, str] = {}

    def register(self, uid: str, token: str) -> None:
        self._token_to_uid[token] = uid

    def get_user(self, token: str):
        uid = self._token_to_uid.get(token)
        if not uid:
            raise Exception("invalid token")
        return type("R", (), {"user": type("U", (), {"id": uid})()})()


class _StubSupabaseClient:
    def __init__(self):
        self.auth = _StubSupabaseAuth()


def _install_supabase_stub(monkeypatch) -> _StubSupabaseClient:
    stub = _StubSupabaseClient()
    monkeypatch.setattr(auth_module, "supabase", stub)
    return stub


# ---------- happy path ----------
def test_register_then_create_pet_flow(client, db, monkeypatch):
    stub = _install_supabase_stub(monkeypatch)

    def fake_register(email, password):
        stub.auth.register("uid-flow-1", "tok-flow-1")
        return _FakeAuthResp(uid="uid-flow-1", token="tok-flow-1")

    monkeypatch.setattr(auth_router, "register_user", fake_register)

    # 1) Register
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "flow@test.com", "password": "Password123!", "name": "Flow User"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    token = body["access_token"]
    assert token == "tok-flow-1"
    assert body["user"]["email"] == "flow@test.com"

    # User row was created with supabase_uid bridged
    user = db.query(models.User).filter_by(email="flow@test.com").first()
    assert user is not None
    assert user.supabase_uid == "uid-flow-1"

    # 2) Create pet using the issued token
    r2 = client.post(
        "/api/v1/pets",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Milo", "species": "Cat", "gender": "Male", "weight_kg": 4.2},
    )
    assert r2.status_code == 200, r2.text
    pet = r2.json()
    assert pet["name"] == "Milo"
    assert pet["species"] == "Cat"
    assert pet["user_id"] == user.id

    # Persisted, scoped to this user
    rows = db.query(models.Pet).filter_by(user_id=user.id).all()
    assert len(rows) == 1 and rows[0].name == "Milo"

    # 3) Frontend HomeScreen calls GET /users/{userId}/pets right after register
    # (now Bearer-authenticated — the endpoint only serves your own user id).
    returned_user_id = body["user"]["id"]
    r3 = client.get(
        f"/api/v1/users/{returned_user_id}/pets",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r3.status_code == 200, r3.text
    listed = r3.json()
    assert len(listed) == 1, (
        "GET /users/{id}/pets returned empty right after register+createPet. "
        "Frontend would render the 'no pets' empty state here."
    )
    assert listed[0]["id"] == pet["id"]
    assert listed[0]["name"] == "Milo"


# ---------- duplicate email blocks both steps ----------
def test_register_duplicate_blocks_pet_creation(client, db, monkeypatch):
    db.add(models.User(email="dup@test.com", name="X", supabase_uid="uid-existing"))
    db.commit()

    monkeypatch.setattr(
        auth_router, "register_user",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call")),
    )

    r = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@test.com", "password": "Password123!", "name": "Dup"},
    )
    assert r.status_code == 409
    # No new user row created
    assert db.query(models.User).filter_by(email="dup@test.com").count() == 1


# ---------- orphan Supabase user: register_user raises, login_user recovers ----------
def test_register_recovers_orphan_supabase_user(client, db, monkeypatch):
    stub = _install_supabase_stub(monkeypatch)

    def boom(email, password):
        raise Exception("user already exists in supabase auth")

    def fake_login(email, password):
        stub.auth.register("uid-orphan", "tok-orphan")
        return _FakeAuthResp(uid="uid-orphan", token="tok-orphan")

    monkeypatch.setattr(auth_router, "register_user", boom)
    monkeypatch.setattr(auth_router, "login_user", fake_login)

    r = client.post(
        "/api/v1/auth/register",
        json={"email": "orphan@test.com", "password": "Password123!", "name": "Orphan"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token == "tok-orphan"

    # And the token actually works for creating a pet
    r2 = client.post(
        "/api/v1/pets",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Buddy", "species": "Dog"},
    )
    assert r2.status_code == 200, r2.text


# ---------- sign_up returns no session (confirmation flow) -> falls back to login for token ----------
def test_register_without_session_falls_back_to_login(client, db, monkeypatch):
    stub = _install_supabase_stub(monkeypatch)

    def fake_register(email, password):
        # No session returned (e.g. email confirmation enabled)
        return _FakeAuthResp(uid="uid-noses", token=None)

    def fake_login(email, password):
        stub.auth.register("uid-noses", "tok-after-login")
        return _FakeAuthResp(uid="uid-noses", token="tok-after-login")

    monkeypatch.setattr(auth_router, "register_user", fake_register)
    monkeypatch.setattr(auth_router, "login_user", fake_login)

    r = client.post(
        "/api/v1/auth/register",
        json={"email": "noses@test.com", "password": "Password123!", "name": "NoSes"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"] == "tok-after-login"


# ---------- create pet requires a valid token ----------
def test_create_pet_without_token_is_unauthorized(client):
    r = client.post("/api/v1/pets", json={"name": "Ghost", "species": "Cat"})
    # HTTPBearer with auto_error=True returns 403 when header is missing
    assert r.status_code in (401, 403)


def test_create_pet_with_invalid_token_is_unauthorized(client, monkeypatch):
    _install_supabase_stub(monkeypatch)  # empty registry -> any token is invalid

    r = client.post(
        "/api/v1/pets",
        headers={"Authorization": "Bearer nonsense"},
        json={"name": "Ghost", "species": "Cat"},
    )
    assert r.status_code == 401


# ============================================================
# Atomic register-with-pet: the onboarding screen sends pet in
# the SAME call as register, so user + pet land in one DB txn.
# ============================================================

def test_register_with_pet_returns_both_atomically(client, db, monkeypatch):
    stub = _install_supabase_stub(monkeypatch)

    def fake_register(email, password):
        stub.auth.register("uid-atomic-1", "tok-atomic-1")
        return _FakeAuthResp(uid="uid-atomic-1", token="tok-atomic-1")

    monkeypatch.setattr(auth_router, "register_user", fake_register)

    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "atomic@test.com",
            "password": "Password123!",
            "name": "Atomic Owner",
            "pet": {
                "name": "Milo",
                "species": "Cat",
                "gender": "Male",
                "weight_kg": 4.2,
                "date_of_birth": "2025-01-01",
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Single response carries token, user, AND the freshly-created pet.
    assert body["access_token"] == "tok-atomic-1"
    assert body["user"]["email"] == "atomic@test.com"
    assert body["pet"] is not None
    assert body["pet"]["name"] == "Milo"
    assert body["pet"]["user_id"] == body["user"]["id"]

    # And GET /users/{id}/pets — what HomeScreen calls — already returns it.
    r2 = client.get(
        f"/api/v1/users/{body['user']['id']}/pets",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["name"] == "Milo"


def test_register_without_pet_still_works(client, db, monkeypatch):
    """Backwards compat: clients that don't send a pet payload behave as before."""
    stub = _install_supabase_stub(monkeypatch)

    def fake_register(email, password):
        stub.auth.register("uid-nopet", "tok-nopet")
        return _FakeAuthResp(uid="uid-nopet", token="tok-nopet")

    monkeypatch.setattr(auth_router, "register_user", fake_register)

    r = client.post(
        "/api/v1/auth/register",
        json={"email": "nopet@test.com", "password": "Password123!", "name": "NoPet"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pet"] is None
    # User row exists, no pet.
    user = db.query(models.User).filter_by(email="nopet@test.com").first()
    assert user is not None
    assert db.query(models.Pet).filter_by(user_id=user.id).count() == 0


def test_register_with_pet_rolls_back_user_when_pet_fails(client, db, monkeypatch):
    """If pet INSERT raises, the user INSERT must rollback too — no orphan user.

    Simulates an unexpected pet-side failure by patching models.Pet to raise
    when the router tries to instantiate it.
    """
    stub = _install_supabase_stub(monkeypatch)

    def fake_register(email, password):
        stub.auth.register("uid-rollback", "tok-rollback")
        return _FakeAuthResp(uid="uid-rollback", token="tok-rollback")

    monkeypatch.setattr(auth_router, "register_user", fake_register)

    real_pet_cls = models.Pet

    def exploding_pet(*args, **kwargs):
        raise RuntimeError("simulated pet insert failure")

    monkeypatch.setattr(auth_router.models, "Pet", exploding_pet)

    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "rollback@test.com",
            "password": "Password123!",
            "name": "Rollback User",
            "pet": {"name": "Buddy", "species": "Dog"},
        },
    )
    assert r.status_code == 500
    assert "Failed to create account" in r.json()["detail"]

    # Critical invariant: NO orphan user left behind.
    monkeypatch.setattr(auth_router.models, "Pet", real_pet_cls)
    assert db.query(models.User).filter_by(email="rollback@test.com").count() == 0
    assert db.query(models.Pet).count() == 0


def test_register_with_pet_atomic_then_home_query_returns_pet(client, db, monkeypatch):
    """End-to-end: simulates exactly what HomeScreen does after the onboarding
    flow — POST /register with pet, then GET /users/{id}/pets. Must return the
    pet so the empty-state never flashes.
    """
    stub = _install_supabase_stub(monkeypatch)

    def fake_register(email, password):
        stub.auth.register("uid-e2e", "tok-e2e")
        return _FakeAuthResp(uid="uid-e2e", token="tok-e2e")

    monkeypatch.setattr(auth_router, "register_user", fake_register)

    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "e2e@test.com",
            "password": "Password123!",
            "name": "E2E",
            "pet": {"name": "Buddy", "species": "Dog", "weight_kg": 10.5},
        },
    )
    assert r.status_code == 200, r.text
    user_id = r.json()["user"]["id"]
    token = r.json()["access_token"]

    # HomeScreen._loadPets() hits this exact endpoint (Bearer-authenticated).
    r2 = client.get(
        f"/api/v1/users/{user_id}/pets",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    pets = r2.json()
    assert len(pets) == 1, "HomeScreen would flash 'no pets' empty state here"
    assert pets[0]["name"] == "Buddy"
