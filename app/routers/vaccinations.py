from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas
from app.database import get_db
from app.auth import get_current_user, require_owned_pet

router = APIRouter(
    prefix="/api/v1",
    tags=["Vaccinations"]
)

@router.post("/vaccinations", response_model=schemas.VaccinationResponse)
def create_vaccination(
    vaccination: schemas.VaccinationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owned_pet(vaccination.pet_id, current_user, db)

    db_vaccination = models.Vaccination(**vaccination.model_dump())
    db.add(db_vaccination)
    db.commit()
    db.refresh(db_vaccination)
    return db_vaccination

@router.get("/pets/{pet_id}/vaccinations", response_model=List[schemas.VaccinationResponse])
def get_pet_vaccinations(
    pet_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, current_user, db)

    vaccinations = db.query(models.Vaccination).filter(models.Vaccination.pet_id == pet_id).all()
    return vaccinations
