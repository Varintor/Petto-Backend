from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Date, Text, Float, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

# ==========================================
# Enums (ตัวแปรแบบเลือกค่าได้)
# ==========================================
class RiskLevel(enum.Enum):
    LOW = "Low Risk"
    MODERATE = "Moderate Risk"
    HIGH = "High Risk"

class ConsultationStatus(enum.Enum):
    PENDING = "Pending"
    ACTIVE = "Active"
    COMPLETED = "Completed"

# ==========================================
# Core Entities (กลุ่มข้อมูลหลัก)
# ==========================================
class User(Base):
    """ตารางเจ้าของสัตว์เลี้ยง (Feature 1: Authentication)"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False) # เตรียมไว้สำหรับระบบ Login
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ความสัมพันธ์: 1 User มีสัตว์เลี้ยงได้หลายตัว
    pets = relationship("Pet", back_populates="owner", cascade="all, delete-orphan")

class Pet(Base):
    """ตารางสัตว์เลี้ยง"""
    __tablename__ = "pets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, index=True, nullable=False)
    species = Column(String) 
    breed = Column(String, nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ความสัมพันธ์
    owner = relationship("User", back_populates="pets")
    assessments = relationship("HealthAssessment", back_populates="pet", cascade="all, delete-orphan")
    activities = relationship("ActivityLog", back_populates="pet", cascade="all, delete-orphan")
    consultations = relationship("Consultation", back_populates="pet", cascade="all, delete-orphan")
    vaccinations = relationship("Vaccination", back_populates="pet", cascade="all, delete-orphan")

# ==========================================
# Phase 1 Features (กำลังพัฒนา)
# ==========================================
class HealthAssessment(Base):
    """ตารางประเมินสุขภาพด้วย AI (Feature 2)"""
    __tablename__ = "health_assessments"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"), nullable=False)
    symptom_description = Column(Text, nullable=False) 
    image_uri = Column(String, nullable=True) # เก็บ URL จาก Supabase
    risk_level = Column(Enum(RiskLevel), nullable=True) 
    ai_raw_response = Column(Text, nullable=True) 
    created_at = Column(DateTime, default=datetime.utcnow)

    pet = relationship("Pet", back_populates="assessments")

class ActivityLog(Base):
    """ตารางบันทึกกิจกรรม (Feature 4 - ห้ามเก็บพิกัด GPS ดิบ)"""
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"), nullable=False)
    activity_type = Column(String, nullable=False) # เช่น Walking, Running
    duration_minutes = Column(Float, nullable=False, default=0.0) 
    distance_meters = Column(Float, nullable=False, default=0.0) 
    is_mission_completed = Column(Boolean, default=False) 
    created_at = Column(DateTime, default=datetime.utcnow)

    pet = relationship("Pet", back_populates="activities")

# ==========================================
# Phase 2 Features (เตรียมโครงสร้างรอไว้)
# ==========================================
class Veterinarian(Base):
    """ตารางสัตวแพทย์"""
    __tablename__ = "veterinarians"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    clinic_name = Column(String, nullable=True)
    license_number = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    consultations = relationship("Consultation", back_populates="vet")

class Consultation(Base):
    """ตารางการให้คำปรึกษา (Feature 3)"""
    __tablename__ = "consultations"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"), nullable=False)
    vet_id = Column(Integer, ForeignKey("veterinarians.id"), nullable=False)
    status = Column(Enum(ConsultationStatus), default=ConsultationStatus.PENDING)
    notes = Column(Text, nullable=True) # บันทึกย่อจากสัตวแพทย์
    created_at = Column(DateTime, default=datetime.utcnow)

    pet = relationship("Pet", back_populates="consultations")
    vet = relationship("Veterinarian", back_populates="consultations")

class Vaccination(Base):
    __tablename__ = "vaccinations"

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, ForeignKey("pets.id"), nullable=False) # เชื่อมกับตาราง pets
    vaccine_name = Column(String, index=True, nullable=False) # ชื่อวัคซีน เช่น พิษสุนัขบ้า, หัดแมว
    date_administered = Column(Date, nullable=False) # วันที่ฉีด
    next_due_date = Column(Date, nullable=True) # วันนัดเข็มต่อไป (ใส่ค่าว่างได้ เผื่อไม่มีนัดต่อ)
    clinic_name = Column(String, nullable=True) # ชื่อคลินิกที่ไปฉีด
    notes = Column(Text, nullable=True) # หมายเหตุ/อาการหลังฉีด
    created_at = Column(DateTime, default=datetime.utcnow)

    # เชื่อมความสัมพันธ์กลับไปหาตาราง Pet
    pet = relationship("Pet", back_populates="vaccinations")