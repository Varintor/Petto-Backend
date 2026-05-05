from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List
from app.models import RiskLevel

# Schema สำหรับข้อมูลที่จะตอบกลับไปให้ Frontend
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

# --- Schemas สำหรับ Vaccination ---

# 1. โครงสร้างข้อมูลที่ผู้ใช้ต้องส่งมาตอนบันทึกวัคซีนเข็มใหม่
class VaccinationCreate(BaseModel):
    pet_id: int
    vaccine_name: str
    date_administered: date
    next_due_date: Optional[date] = None
    clinic_name: Optional[str] = None
    notes: Optional[str] = None

# 2. โครงสร้างข้อมูลที่ระบบจะส่งกลับไปให้แอป (เพิ่ม id และเวลาที่สร้าง)
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
        from_attributes = True  # (ถ้าเกิด Error ตอนรัน ลองเปลี่ยนเป็น orm_mode = True นะครับ)