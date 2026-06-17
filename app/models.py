from sqlalchemy import (
    Column, BigInteger, String, DateTime, Date, ForeignKey, Enum, Text,
    Float, Boolean, Numeric, UniqueConstraint, CheckConstraint, func, text,
)
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()

# ==========================================
# Enums  (must match the Supabase native enum types in srs_schema_v1)
# ==========================================
# NOTE on storage:
#  - SQLAlchemy persists the enum MEMBER NAME by default. RiskLevel/
#    ConsultationStatus member names are UPPERCASE and match their DB labels.
#  - MessageSender/ActivitySource DB labels are lowercase, so we use
#    values_callable to persist the enum VALUE instead of the name.

class RiskLevel(enum.Enum):
    LOW = "Low Risk"
    MODERATE = "Moderate Risk"
    HIGH = "High Risk"

class ConsultationStatus(enum.Enum):
    PENDING = "Pending"
    ACTIVE = "Active"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"

class MessageSender(enum.Enum):
    USER = "user"
    VET = "vet"

class ActivitySource(enum.Enum):
    PHONE = "phone"
    DEVICE = "device"


# Reusable enum column types bound to the existing Supabase types by name.
RiskLevelType = Enum(RiskLevel, name="risk_level")
ConsultationStatusType = Enum(ConsultationStatus, name="consultation_status")
MessageSenderType = Enum(
    MessageSender, name="message_sender",
    values_callable=lambda e: [m.value for m in e],
)
ActivitySourceType = Enum(
    ActivitySource, name="activity_source",
    values_callable=lambda e: [m.value for m in e],
)


# ==========================================
# Feature 1: Auth & Profile
# ==========================================
class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    supabase_uid = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=True)
    name = Column(String, nullable=True)
    avatar_uri = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    pets = relationship("Pet", back_populates="owner", cascade="all, delete-orphan")


class Pet(Base):
    __tablename__ = "pet_profiles"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    species = Column(String, nullable=True)
    breed = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    weight_kg = Column(Numeric(5, 2), nullable=True)
    avatar_uri = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="pets")
    assessments = relationship("HealthAssessment", back_populates="pet", cascade="all, delete-orphan")
    activities = relationship("ActivityLog", back_populates="pet", cascade="all, delete-orphan")
    consultations = relationship("Consultation", back_populates="pet", cascade="all, delete-orphan")
    vaccinations = relationship("Vaccination", back_populates="pet", cascade="all, delete-orphan")
    missions = relationship("DailyMission", back_populates="pet", cascade="all, delete-orphan")


# ==========================================
# Feature 2: AI Health Assessment
# ==========================================
class HealthAssessment(Base):
    __tablename__ = "health_assessments"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    symptom_description = Column(Text, nullable=False)
    image_uri = Column(String, nullable=True)
    risk_level = Column(RiskLevelType, nullable=True)
    ai_raw_response = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="assessments")


# ==========================================
# Feature 3: Vet Consultation (+ chat messages)
# ==========================================
class Veterinarian(Base):
    __tablename__ = "veterinarians"

    id = Column(BigInteger, primary_key=True)
    # Bridges this row to Supabase Auth (matches users.supabase_uid behaviour).
    # Nullable so legacy rows created before the Supabase-Auth flow can exist.
    supabase_uid = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True, nullable=False)
    # Retained nullable for backwards-compatibility with rows that pre-date the
    # Supabase-Auth migration. New vet accounts authenticate via Supabase Auth
    # and leave this column NULL.
    password_hash = Column(String, nullable=True)
    name = Column(String, nullable=False)
    clinic_name = Column(String, nullable=True)
    license_number = Column(String, unique=True, nullable=True)
    specialty = Column(String, nullable=True)
    avatar_uri = Column(String, nullable=True)
    is_online = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    consultations = relationship("Consultation", back_populates="vet")


class Consultation(Base):
    __tablename__ = "consultations"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    vet_id = Column(BigInteger, ForeignKey("veterinarians.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(ConsultationStatusType, nullable=False, server_default=text("'PENDING'"))
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="consultations")
    vet = relationship("Veterinarian", back_populates="consultations")
    messages = relationship("Message", back_populates="consultation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(BigInteger, primary_key=True)
    consultation_id = Column(BigInteger, ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_type = Column(MessageSenderType, nullable=False)
    sender_id = Column(BigInteger, nullable=True)
    content = Column(Text, nullable=True)
    attachment_uri = Column(String, nullable=True)
    is_read = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    consultation = relationship("Consultation", back_populates="messages")

    __table_args__ = (
        CheckConstraint("content IS NOT NULL OR attachment_uri IS NOT NULL", name="messages_has_payload"),
    )


# ==========================================
# Feature 4: Daily Missions & GPS Activity
# ==========================================
class DailyMission(Base):
    __tablename__ = "daily_missions"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    mission_date = Column(Date, nullable=False, server_default=func.current_date())
    title = Column(String, nullable=False)
    mission_type = Column(String, nullable=False, server_default=text("'walk'"))
    target_value = Column(Numeric, nullable=True)
    unit = Column(String, nullable=True)
    reward = Column(String, nullable=True)
    is_completed = Column(Boolean, nullable=False, server_default=text("false"))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="missions")
    activities = relationship("ActivityLog", back_populates="mission")

    __table_args__ = (
        UniqueConstraint("pet_id", "mission_date", "mission_type", name="uq_mission_per_day"),
    )


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    mission_id = Column(BigInteger, ForeignKey("daily_missions.id", ondelete="SET NULL"), nullable=True)
    source = Column(ActivitySourceType, nullable=False, server_default=text("'phone'"))
    activity_type = Column(String, nullable=False)
    duration_minutes = Column(Float, nullable=False, server_default=text("0"))
    distance_meters = Column(Float, nullable=False, server_default=text("0"))
    calories_burned = Column(Float, nullable=True)
    avg_speed_kmh = Column(Float, nullable=True)
    max_speed_kmh = Column(Float, nullable=True)
    steps = Column(BigInteger, nullable=True)
    # NOTE: raw GPS route is NOT persisted (Petto proposal §3.7).
    # Only aggregated metrics (distance, duration, speed) are stored here.
    notes = Column(Text, nullable=True)
    is_mission_completed = Column(Boolean, nullable=False, server_default=text("false"))
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="activities")
    mission = relationship("DailyMission", back_populates="activities")


# ==========================================
# Vaccinations
# ==========================================
class Vaccination(Base):
    __tablename__ = "vaccinations"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    vaccine_name = Column(String, index=True, nullable=False)
    date_administered = Column(Date, nullable=False)
    next_due_date = Column(Date, nullable=True)
    clinic_name = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="vaccinations")
