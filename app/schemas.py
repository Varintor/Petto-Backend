from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional, List
from app.models import RiskLevel

# ==========================================
# Auth
# ==========================================

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    # When the onboarding screen collects pet info up-front it sends it here so
    # the backend can create the user + pet in a single DB transaction. If the
    # pet insert fails the user insert is rolled back too — guarantees the app
    # never sees "registered but no pet" half-states.
    pet: Optional["PetCreate"] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    avatar_uri: Optional[str] = None

    class Config:
        from_attributes = True

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    # Populated when the register call also created a pet atomically.
    pet: Optional["PetResponse"] = None

# ==========================================
# Feature 2: Health Assessment
# ==========================================

class AssessmentResponse(BaseModel):
    id: int
    pet_id: int
    symptom_description: str
    image_uri: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    ai_raw_response: Optional[str] = None
    status: str
    error_code: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# Feature 1: Pet Profile
# ==========================================

class PetCreate(BaseModel):
    name: str
    species: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    weight_kg: Optional[float] = None
    blood_type: Optional[str] = None
    avatar_uri: Optional[str] = None

class PetUpdate(BaseModel):
    name: Optional[str] = None
    species: Optional[str] = None
    breed: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[date] = None
    weight_kg: Optional[float] = None
    blood_type: Optional[str] = None
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
    blood_type: Optional[str] = None
    avatar_uri: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Resolve the forward references that RegisterRequest / AuthResponse hold to
# PetCreate / PetResponse (declared after them so the Auth section stays at
# the top of the file).
RegisterRequest.model_rebuild()
AuthResponse.model_rebuild()

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
