from sqlalchemy import (
    Column, BigInteger, Integer, String, DateTime, Date, ForeignKey, Enum, Text,
    Float, Boolean, Numeric, UniqueConstraint, CheckConstraint, Index, JSON, Uuid,
    func, text,
)
from sqlalchemy.orm import declarative_base, relationship
import enum
import uuid

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
    AI = "ai"  # server-generated AI assist summaries (Feature 3)

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
    supabase_uid = Column(String, unique=True, nullable=True)
    email = Column(String, unique=True, nullable=False)
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
    blood_type = Column(String, nullable=True)  # A | B | AB | O
    avatar_uri = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="pets")
    assessments = relationship("HealthAssessment", back_populates="pet", cascade="all, delete-orphan")
    activities = relationship("ActivityLog", back_populates="pet", cascade="all, delete-orphan")
    consultations = relationship("Consultation", back_populates="pet", cascade="all, delete-orphan")
    vaccinations = relationship("Vaccination", back_populates="pet", cascade="all, delete-orphan")
    missions = relationship("DailyMission", back_populates="pet", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="pet", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="pet", cascade="all, delete-orphan")
    wardrobe_items = relationship("PetWardrobeItem", back_populates="pet", cascade="all, delete-orphan")
    health_profile = relationship(
        "PetHealthProfile", back_populates="pet", cascade="all, delete-orphan", uselist=False
    )
    appointments = relationship("Appointment", back_populates="pet", cascade="all, delete-orphan")


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
    status = Column(String(20), nullable=False, server_default=text("'completed'"))
    error_code = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="assessments")

    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'failed')",
            name="health_assessments_valid_status",
        ),
    )


# ==========================================
# Feature 3: Vet Consultation (+ chat messages)
# ==========================================
class Veterinarian(Base):
    __tablename__ = "veterinarians"

    id = Column(BigInteger, primary_key=True)
    # Bridges this row to Supabase Auth (matches users.supabase_uid behaviour).
    # Nullable so legacy rows created before the Supabase-Auth flow can exist.
    supabase_uid = Column(String, unique=True, nullable=True)
    email = Column(String, unique=True, nullable=False)
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
    verification_status = Column(String(20), nullable=False, server_default=text("'pending'"))
    is_accepting_consultations = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    consultations = relationship("Consultation", back_populates="vet")
    provider_links = relationship(
        "ProviderVeterinarian", back_populates="veterinarian", cascade="all, delete-orphan"
    )
    proposed_appointments = relationship("Appointment", back_populates="proposed_by_vet")

    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('pending', 'approved', 'rejected', 'disabled')",
            name="veterinarians_valid_verification_status",
        ),
    )


class VeterinaryProvider(Base):
    __tablename__ = "veterinary_providers"

    id = Column(BigInteger, primary_key=True)
    external_place_id = Column(String(255), unique=True, nullable=True)
    name = Column(String(200), nullable=False)
    provider_type = Column(String(30), nullable=False, server_default=text("'hospital'"))
    address = Column(Text, nullable=True)
    phone = Column(String(50), nullable=True)
    latitude = Column(Numeric(9, 6), nullable=True)
    longitude = Column(Numeric(9, 6), nullable=True)
    operating_hours = Column(JSON, nullable=True)
    provider_status = Column(String(20), nullable=False, server_default=text("'listed'"))
    consultation_enabled = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    veterinarian_links = relationship(
        "ProviderVeterinarian", back_populates="provider", cascade="all, delete-orphan"
    )
    consultations = relationship("Consultation", back_populates="provider")
    appointments = relationship("Appointment", back_populates="provider")

    __table_args__ = (
        CheckConstraint(
            "provider_type IN ('hospital', 'clinic', 'independent')",
            name="veterinary_providers_valid_type",
        ),
        CheckConstraint(
            "provider_status IN ('listed', 'partner', 'disabled')",
            name="veterinary_providers_valid_status",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="veterinary_providers_valid_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="veterinary_providers_valid_longitude",
        ),
    )


class ProviderVeterinarian(Base):
    __tablename__ = "provider_veterinarians"

    provider_id = Column(
        BigInteger, ForeignKey("veterinary_providers.id", ondelete="CASCADE"), primary_key=True
    )
    veterinarian_id = Column(
        BigInteger, ForeignKey("veterinarians.id", ondelete="CASCADE"), primary_key=True
    )
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    accepting_consultations = Column(Boolean, nullable=False, server_default=text("false"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    provider = relationship("VeterinaryProvider", back_populates="veterinarian_links")
    veterinarian = relationship("Veterinarian", back_populates="provider_links")


class Consultation(Base):
    __tablename__ = "consultations"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    vet_id = Column(BigInteger, ForeignKey("veterinarians.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(
        BigInteger, ForeignKey("veterinary_providers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status = Column(ConsultationStatusType, nullable=False, server_default=text("'PENDING'"))
    # Optional link to the AI assessment being forwarded to the vet (UD-06).
    assessment_id = Column(
        BigInteger, ForeignKey("health_assessments.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    subject = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

    pet = relationship("Pet", back_populates="consultations")
    vet = relationship("Veterinarian", back_populates="consultations")
    provider = relationship("VeterinaryProvider", back_populates="consultations")
    messages = relationship("Message", back_populates="consultation", cascade="all, delete-orphan")
    shared_assessments = relationship(
        "ConsultationSharedAssessment", back_populates="consultation", cascade="all, delete-orphan"
    )
    appointments = relationship("Appointment", back_populates="consultation", cascade="all, delete-orphan")
    shared_health_cards = relationship(
        "ConsultationSharedHealthCard", back_populates="consultation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(BigInteger, primary_key=True)
    consultation_id = Column(BigInteger, ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_type = Column(MessageSenderType, nullable=False)
    sender_id = Column(BigInteger, nullable=True)
    content = Column(Text, nullable=True)
    attachment_uri = Column(String, nullable=True)
    is_read = Column(Boolean, nullable=False, server_default=text("false"))
    client_message_id = Column(Uuid(as_uuid=True), nullable=True, default=uuid.uuid4)
    message_type = Column(String(20), nullable=False, server_default=text("'text'"))
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    consultation = relationship("Consultation", back_populates="messages")

    __table_args__ = (
        CheckConstraint("content IS NOT NULL OR attachment_uri IS NOT NULL", name="messages_has_payload"),
        CheckConstraint(
            "message_type IN ('text', 'assessment', 'appointment', 'system', 'ai')",
            name="messages_valid_message_type",
        ),
        UniqueConstraint(
            "consultation_id", "client_message_id", name="uq_messages_consultation_client_id"
        ),
    )


class ConsultationSharedAssessment(Base):
    __tablename__ = "consultation_shared_assessments"

    id = Column(BigInteger, primary_key=True)
    consultation_id = Column(
        BigInteger, ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_id = Column(
        BigInteger, ForeignKey("health_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_by_user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shared_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    consultation = relationship("Consultation", back_populates="shared_assessments")
    assessment = relationship("HealthAssessment")
    shared_by = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "consultation_id", "assessment_id", name="uq_consultation_shared_assessment"
        ),
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(BigInteger, primary_key=True)
    consultation_id = Column(
        BigInteger, ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id = Column(
        BigInteger, ForeignKey("veterinary_providers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    proposed_by_vet_id = Column(
        BigInteger, ForeignKey("veterinarians.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, server_default=text("'proposed'"))
    responded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    consultation = relationship("Consultation", back_populates="appointments")
    pet = relationship("Pet", back_populates="appointments")
    provider = relationship("VeterinaryProvider", back_populates="appointments")
    proposed_by_vet = relationship("Veterinarian", back_populates="proposed_appointments")
    calendar_event = relationship(
        "CalendarEvent", back_populates="appointment", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'accepted', 'declined', 'cancelled', 'completed')",
            name="appointments_valid_status",
        ),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="appointments_valid_time_range"),
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


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    event_type = Column(String(30), nullable=False)
    event_date = Column(Date, nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    is_completed = Column(Boolean, nullable=False, server_default=text("false"))
    reminder_minutes = Column(Integer, nullable=True, server_default=text("30"))
    appointment_id = Column(
        BigInteger,
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="calendar_events")
    appointment = relationship("Appointment", back_populates="calendar_event")

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('care', 'medication', 'vet', 'grooming', 'walk')",
            name="calendar_events_valid_type",
        ),
        CheckConstraint(
            "reminder_minutes IS NULL OR reminder_minutes BETWEEN 0 AND 10080",
            name="calendar_events_valid_reminder",
        ),
    )


class PetWardrobeItem(Base):
    __tablename__ = "pet_wardrobe_items"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    accessory_id = Column(String(64), nullable=False)
    unlocked_at = Column(DateTime(timezone=True), server_default=func.now())
    equipped_at = Column(DateTime(timezone=True), nullable=True)

    pet = relationship("Pet", back_populates="wardrobe_items")

    __table_args__ = (
        UniqueConstraint("pet_id", "accessory_id", name="uq_pet_wardrobe_item"),
        Index(
            "uq_pet_wardrobe_one_equipped",
            "pet_id",
            unique=True,
            postgresql_where=equipped_at.is_not(None),
            sqlite_where=equipped_at.is_not(None),
        ),
    )


class PetHealthProfile(Base):
    __tablename__ = "pet_health_profiles"

    pet_id = Column(
        BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    allergies = Column(JSON, nullable=False, default=list)
    chronic_conditions = Column(JSON, nullable=False, default=list)
    current_medications = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="health_profile")


class ConsultationSharedHealthCard(Base):
    __tablename__ = "consultation_shared_health_cards"

    id = Column(BigInteger, primary_key=True)
    consultation_id = Column(
        BigInteger, ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_by_user_id = Column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    snapshot = Column(JSON, nullable=False)
    shared_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    consultation = relationship("Consultation", back_populates="shared_health_cards")
    pet = relationship("Pet")
    shared_by = relationship("User")


# ==========================================
# Feature 4 - Mode B: paired tracking devices (BLE/GPS collar)
# ==========================================
class Device(Base):
    __tablename__ = "devices"

    id = Column(BigInteger, primary_key=True)
    pet_id = Column(BigInteger, ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)                      # user-facing label
    device_type = Column(String, nullable=False, server_default=text("'ble_collar'"))
    identifier = Column(String, unique=True, nullable=False)   # MAC / serial
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    battery_percent = Column(Integer, nullable=True)
    # Only the LATEST position is stored (live-map pin, SRS-F4-037/038).
    # The raw route is never persisted - proposal privacy rule (see
    # activity_logs note above); telemetry is aggregated on ingest.
    last_lat = Column(Float, nullable=True)
    last_lng = Column(Float, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    paired_at = Column(DateTime(timezone=True), server_default=func.now())

    pet = relationship("Pet", back_populates="devices")
