# -*- coding: utf-8 -*-
import pytest
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app import models

# ITC-02: Pet Profile Relational Integrity and Constraints
# Test ID: pet_profile_db_relational_integrity

def test_create_pet_valid_owner_id(client, db, auth_client, user):
    """ITC-02-TC-01: Create pet with valid Owner ID succeeds"""
    # User is automatically created and logged in via `auth_client` & `user` fixtures
    pet_data = {
        "name": "Valid Pet",
        "species": "Dog",
        "weight_kg": 15.0
    }
    
    response = auth_client.post("/api/v1/pets", json=pet_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == "Valid Pet"
    
    # Verify in DB directly
    db_pet = db.query(models.Pet).filter(models.Pet.id == data["id"]).first()
    assert db_pet is not None
    assert db_pet.user_id == user.id


def test_create_pet_non_existent_owner_id(db):
    """ITC-02-TC-02: Create pet with non-existent Owner ID fails"""
    # Try to insert directly into DB to test relational constraints
    pet = models.Pet(
        name="Invalid Pet",
        species="Cat",
        user_id=999  # Does not exist
    )
    db.add(pet)
    
    # SQLite enforces foreign keys if PRAGMA foreign_keys = ON, but SQLAlchemy
    # models might catch it or DB might catch it.
    with pytest.raises(IntegrityError):
        # We need to manually execute pragma for SQLite in tests if we want strict FKs
        # Or just rely on SQLAlchemy throwing IntegrityError.
        db.execute(models.text("PRAGMA foreign_keys=ON"))
        db.commit()
    
    db.rollback()


def test_user_deletion_cascades_to_pet_profiles(db, user):
    """ITC-02-TC-03: User deletion cascades to pet profiles"""
    # Enable foreign keys for SQLite just to be sure cascade works
    db.execute(models.text("PRAGMA foreign_keys=ON"))
    
    # Add two pets linked to the user
    pet1 = models.Pet(name="Pet 1", species="Dog", user_id=user.id)
    pet2 = models.Pet(name="Pet 2", species="Cat", user_id=user.id)
    db.add_all([pet1, pet2])
    db.commit()
    
    # Verify pets exist
    pets = db.query(models.Pet).filter(models.Pet.user_id == user.id).all()
    assert len(pets) == 2
    
    # Delete the user
    db.delete(user)
    db.commit()
    
    # Verify pets are gone
    remaining_pets = db.query(models.Pet).filter(models.Pet.user_id == user.id).all()
    assert len(remaining_pets) == 0
