from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, require_owned_pet
from app.database import get_db
from app.utils.time import now_bkk

router = APIRouter(prefix="/api/v1", tags=["Wardrobe"])


class WardrobeItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    accessory_id: str
    unlocked_at: datetime
    equipped_at: datetime | None


@router.get("/pets/{pet_id}/wardrobe-items", response_model=list[WardrobeItemResponse])
def list_wardrobe_items(
    pet_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, user, db)
    return db.query(models.PetWardrobeItem).filter_by(pet_id=pet_id).order_by(
        models.PetWardrobeItem.unlocked_at.desc()
    ).all()


@router.put("/pets/{pet_id}/wardrobe-items/{accessory_id}/equip", response_model=WardrobeItemResponse)
def equip_wardrobe_item(
    pet_id: int,
    accessory_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, user, db)
    item = db.query(models.PetWardrobeItem).filter_by(
        pet_id=pet_id, accessory_id=accessory_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Wardrobe item not unlocked")
    db.query(models.PetWardrobeItem).filter(
        models.PetWardrobeItem.pet_id == pet_id,
        models.PetWardrobeItem.id != item.id,
    ).update({models.PetWardrobeItem.equipped_at: None}, synchronize_session=False)
    item.equipped_at = now_bkk()
    db.commit()
    db.refresh(item)
    return item


@router.delete("/pets/{pet_id}/wardrobe-items/equipped", status_code=204)
def unequip_wardrobe_item(
    pet_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_owned_pet(pet_id, user, db)
    db.query(models.PetWardrobeItem).filter_by(pet_id=pet_id).update(
        {models.PetWardrobeItem.equipped_at: None}, synchronize_session=False
    )
    db.commit()
