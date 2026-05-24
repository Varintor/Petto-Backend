from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas
from app.database import get_db

router = APIRouter(
    prefix="/api/v1",
    tags=["Pets (สัตว์เลี้ยง)"]
)


@router.post("/pets", response_model=schemas.PetResponse)
def create_pet(pet: schemas.PetCreate, db: Session = Depends(get_db)):
    """
    สร้างโปรไฟล์สัตว์เลี้ยงใหม่
    """
    user = db.query(models.User).filter(models.User.id == pet.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้ในระบบ")

    db_pet = models.Pet(**pet.model_dump())
    db.add(db_pet)
    db.commit()
    db.refresh(db_pet)
    return db_pet


@router.get("/pets", response_model=List[schemas.PetResponse])
def get_all_pets(db: Session = Depends(get_db)):
    """
    ดูรายการสัตว์เลี้ยงทั้งหมดในระบบ
    """
    pets = db.query(models.Pet).all()
    return pets


@router.get("/pets/{pet_id}", response_model=schemas.PetResponse)
def get_pet(pet_id: int, db: Session = Depends(get_db)):
    """
    ดูข้อมูลสัตว์เลี้ยงตัวเดียว
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")
    return pet


@router.get("/users/{user_id}/pets", response_model=List[schemas.PetResponse])
def get_user_pets(user_id: int, db: Session = Depends(get_db)):
    """
    ดูรายการสัตว์เลี้ยงทั้งหมดของผู้ใช้คนหนึ่ง
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="ไม่พบผู้ใช้ในระบบ")

    pets = db.query(models.Pet).filter(models.Pet.user_id == user_id).all()
    return pets


@router.put("/pets/{pet_id}", response_model=schemas.PetResponse)
def update_pet(pet_id: int, pet_update: schemas.PetUpdate, db: Session = Depends(get_db)):
    """
    แก้ไขข้อมูลสัตว์เลี้ยง
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    update_data = pet_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pet, field, value)

    db.commit()
    db.refresh(pet)
    return pet


@router.delete("/pets/{pet_id}")
def delete_pet(pet_id: int, db: Session = Depends(get_db)):
    """
    ลบสัตว์เลี้ยง
    """
    pet = db.query(models.Pet).filter(models.Pet.id == pet_id).first()
    if not pet:
        raise HTTPException(status_code=404, detail="ไม่พบสัตว์เลี้ยงในระบบ")

    db.delete(pet)
    db.commit()
    return {"message": "ลบสัตว์เลี้ยงเรียบร้อยแล้ว"}
