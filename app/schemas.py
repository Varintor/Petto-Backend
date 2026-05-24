from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List
from app.models import RiskLevel

# ==========================================
# Feature 2: Health Assessment
# ==========================================

class AssessmentResponse(BaseModel):
    id: int
    pet_id: int
    symptom_description: str
    image_uri: Optional[str] = None
    risk_level: RiskLevel
    ai_raw_response: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# Feature 1: Pet Profile
# ==========================================

class PetCreate(BaseModel):
    user_id: int
    name: str
    species: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    weight_kg: Optional[float] = None
    avatar_uri: Optional[str] = None

class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    weight_kg: Optional[float] = None
    avatar_uri: Optional[str] = None

class PetResponse(BaseModel):
    id: int
    user_id: int
    name: str
    species: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    weight_kg: Optional[float] = None
    avatar_uri: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ==========================================
# Vaccinations
# ==========================================

class VaccinationCreate(BaseModel):
    pet_id: int
    vaccine_name: str
    date_administered: date
    next_due_date: Optional[date] = None
    clinic_name: Optional[str] = None
    notes: Optional[str] = None

class VaccinationResponse(BaseModel):
    id: int
    pet_id: int
    vaccine_name: str
    date_administered: date
    next_due_date: Optional[date] = None
    clinic_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
