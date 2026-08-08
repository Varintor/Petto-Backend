from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas
from app.database import get_db
from app.auth import get_current_user, require_owned_pet

router = APIRouter(
    prefix="/api/v1",
    tags=["Pets"]
)


@router.post("/pets", response_model=schemas.PetResponse)
def create_pet(
    pet: schemas.PetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_pet = models.Pet(user_id=current_user.id, **pet.model_dump())
    db.add(db_pet)
    db.commit()
    db.refresh(db_pet)
    return db_pet


@router.get("/pets", response_model=List[schemas.PetResponse])
def get_my_pets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List the authenticated user's pets."""
    return db.query(models.Pet).filter(models.Pet.user_id == current_user.id).all()


@router.get("/pets/{pet_id}", response_model=schemas.PetResponse)
def get_pet(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get a single pet by ID (owner only)."""
    return require_owned_pet(pet_id, current_user, db)


@router.get("/users/{user_id}/pets", response_model=List[schemas.PetResponse])
def get_user_pets(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List all pets belonging to a user (only your own user id)."""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    pets = db.query(models.Pet).filter(models.Pet.user_id == user_id).all()
    return pets


@router.put("/pets/{pet_id}", response_model=schemas.PetResponse)
def update_pet(
    pet_id: int,
    pet_update: schemas.PetUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Update a pet's profile (owner only)."""
    pet = require_owned_pet(pet_id, current_user, db)

    update_data = pet_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pet, field, value)

    db.commit()
    db.refresh(pet)
    return pet


@router.delete("/pets/{pet_id}")
def delete_pet(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Delete a pet (owner only)."""
    pet = require_owned_pet(pet_id, current_user, db)

    db.delete(pet)
    db.commit()
    return {"message": "Pet deleted"}
