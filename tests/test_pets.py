# -*- coding: utf-8 -*-
"""UTC-03 / UTC-04: Pet Management module."""


# ---- UTC-03: create / read ----
def test_create_pet(auth_client, user):
    r = auth_client.post("/api/v1/pets",
                         json={"name": "Buddy", "species": "Dog", "weight_kg": 12.5,
                               "blood_type": "A"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["id"]
    assert data["user_id"] == user.id
    assert data["name"] == "Buddy"
    assert data["species"] == "Dog"
    # blood_type used to be silently dropped (no column) - must round-trip now.
    assert data["blood_type"] == "A"


def test_get_pet_not_found(auth_client):
    r = auth_client.get("/api/v1/pets/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "Pet not found"


# ---- UTC-04: update / delete ----
def test_update_pet(auth_client, pet):
    r = auth_client.put(f"/api/v1/pets/{pet.id}", json={"name": "Max", "weight_kg": 10.5})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "Max"
    assert data["weight_kg"] == 10.5


def test_delete_pet(auth_client, pet):
    assert auth_client.delete(f"/api/v1/pets/{pet.id}").status_code == 200
    assert auth_client.get(f"/api/v1/pets/{pet.id}").status_code == 404
