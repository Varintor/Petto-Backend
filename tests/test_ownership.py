# -*- coding: utf-8 -*-
"""Cross-account isolation (URS-F2-09 / SRS-F2-023 / SRS-F4-045).

Another authenticated user must not be able to read or mutate pets,
missions, activities, stats, or assessments that belong to someone else.
Non-owned resources return the same 404 as missing ones so ids don't leak.
"""
import pytest

from app import models
from app.auth import (
    SupabaseAuthContext,
    get_current_user,
    get_supabase_auth_context,
    get_supabase_uid,
)
from app.main import app


@pytest.fixture()
def intruder(db):
    u = models.User(email="intruder@test.com", name="Intruder", supabase_uid="uid-intruder")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def intruder_client(client, intruder):
    """A client authenticated as a DIFFERENT user than the `pet` owner."""
    app.dependency_overrides[get_current_user] = lambda: intruder
    app.dependency_overrides[get_supabase_auth_context] = lambda: SupabaseAuthContext(
        supabase_uid=intruder.supabase_uid,
        access_token="intruder-test-token",
    )
    app.dependency_overrides[get_supabase_uid] = lambda: intruder.supabase_uid
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_supabase_auth_context, None)
    app.dependency_overrides.pop(get_supabase_uid, None)


def test_cannot_read_another_users_pet(intruder_client, pet):
    r = intruder_client.get(f"/api/v1/pets/{pet.id}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Pet not found"


def test_cannot_update_or_delete_another_users_pet(intruder_client, pet):
    assert intruder_client.put(
        f"/api/v1/pets/{pet.id}", json={"name": "Hacked"}
    ).status_code == 404
    assert intruder_client.delete(f"/api/v1/pets/{pet.id}").status_code == 404


def test_cannot_list_another_users_pets(intruder_client, user, pet):
    r = intruder_client.get(f"/api/v1/users/{user.id}/pets")
    assert r.status_code == 403


def test_cannot_read_another_users_missions(intruder_client, pet):
    assert intruder_client.get(
        f"/api/v1/pets/{pet.id}/missions/today"
    ).status_code == 404
    assert intruder_client.post(
        f"/api/v1/pets/{pet.id}/missions/seed-today"
    ).status_code == 404


def test_cannot_complete_another_users_mission(intruder_client, pet, db):
    from app.utils.time import today_bkk

    mission = models.DailyMission(
        pet_id=pet.id, mission_date=today_bkk(),
        title="Walk for 15 minutes", mission_type="walk",
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)

    r = intruder_client.put(f"/api/v1/missions/{mission.id}/complete")
    assert r.status_code == 404
    db.refresh(mission)
    assert mission.is_completed is False


def test_cannot_read_another_users_stats_or_assessments(intruder_client, pet):
    assert intruder_client.get(
        f"/api/v1/pets/{pet.id}/stats/dashboard"
    ).status_code == 404
    assert intruder_client.get(
        f"/api/v1/pets/{pet.id}/assessments"
    ).status_code == 404
