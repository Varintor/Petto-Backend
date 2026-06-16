from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas
from app.database import get_db
from app.auth import get_current_user

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
def get_all_pets(db: Session = Depends(get_db)):
    """List all pets."""
    pets = db.query(models.Pet).all()
    return pets


@router.get("/pets/{pet_id}", response_model=schemas.PetResponse)
def get_pet(pet_id: int, db: Session = Depends(get_db)):
    """Get a single pet by ID."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")
    return pet


@router.get("/users/{user_id}/pets", response_model=List[schemas.PetResponse])
def get_user_pets(user_id: int, db: Session = Depends(get_db)):
    """List all pets belonging to a user."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pets = db.query(models.Pet).filter(models.Pet.user_id == user_id).all()
    return pets


@router.put("/pets/{pet_id}", response_model=schemas.PetResponse)
def update_pet(pet_id: int, pet_update: schemas.PetUpdate, db: Session = Depends(get_db)):
    """Update a pet's profile."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    update_data = pet_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pet, field, value)

    db.commit()
    db.refresh(pet)
    return pet


@router.delete("/pets/{pet_id}")
def delete_pet(pet_id: int, db: Session = Depends(get_db)):
    """Delete a pet."""
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="Pet not found")

    db.delete(pet)
    db.commit()
    return {"message": "Pet deleted"}
