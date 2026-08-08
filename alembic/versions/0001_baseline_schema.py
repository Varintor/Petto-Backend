"""baseline: adopt existing Supabase schema (srs_schema_v1)

This is a fresh, single baseline that mirrors the REAL production schema
(app/models.py is the source of truth). It replaces the previous migrations
(`b8cdf7bcae04`, `d65684bb677a`) which had drifted badly from the live DB —
they created a `pets` table that does not exist (the real table is
`pet_profiles`) and were missing most columns/tables.

The production database is STAMPED at this revision (see
`alembic_version.version_num`), so `alembic upgrade head` is a no-op there.
On a fresh/empty database, `alembic upgrade head` rebuilds the full schema.

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-07-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_baseline_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enum types already exist in production; create_type=False keeps create_table
# from re-emitting CREATE TYPE. We create them explicitly (checkfirst) below.
risk_level = postgresql.ENUM(
    "LOW", "MODERATE", "HIGH", name="risk_level", create_type=False
)
consultation_status = postgresql.ENUM(
    "PENDING", "ACTIVE", "COMPLETED", "CANCELLED",
    name="consultation_status", create_type=False,
)
message_sender = postgresql.ENUM(
    "user", "vet", name="message_sender", create_type=False
)
activity_source = postgresql.ENUM(
    "phone", "device", name="activity_source", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    risk_level.create(bind, checkfirst=True)
    consultation_status.create(bind, checkfirst=True)
    message_sender.create(bind, checkfirst=True)
    activity_source.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("supabase_uid", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("avatar_uri", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("supabase_uid"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_supabase_uid", "users", ["supabase_uid"], unique=True)

    op.create_table(
        "veterinarians",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("supabase_uid", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("clinic_name", sa.String(), nullable=True),
        sa.Column("license_number", sa.String(), nullable=True),
        sa.Column("specialty", sa.String(), nullable=True),
        sa.Column("avatar_uri", sa.String(), nullable=True),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("license_number"),
        sa.UniqueConstraint("supabase_uid"),
    )
    op.create_index("ix_veterinarians_email", "veterinarians", ["email"], unique=True)
    op.create_index("ix_veterinarians_supabase_uid", "veterinarians", ["supabase_uid"], unique=True)

    op.create_table(
        "pet_profiles",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("species", sa.String(), nullable=True),
        sa.Column("breed", sa.String(), nullable=True),
        sa.Column("gender", sa.String(), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(5, 2), nullable=True),
        sa.Column("avatar_uri", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pet_profiles_user_id", "pet_profiles", ["user_id"])

    op.create_table(
        "health_assessments",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("symptom_description", sa.Text(), nullable=False),
        sa.Column("image_uri", sa.String(), nullable=True),
        sa.Column("risk_level", risk_level, nullable=True),
        sa.Column("ai_raw_response", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_health_assessments_pet_id", "health_assessments", ["pet_id"])

    op.create_table(
        "consultations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("vet_id", sa.BigInteger(), nullable=False),
        sa.Column("status", consultation_status, nullable=False,
                  server_default=sa.text("'PENDING'::consultation_status")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vet_id"], ["veterinarians.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consultations_pet_id", "consultations", ["pet_id"])
    op.create_index("ix_consultations_vet_id", "consultations", ["vet_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("consultation_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_type", message_sender, nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("attachment_uri", sa.String(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "content IS NOT NULL OR attachment_uri IS NOT NULL",
            name="messages_has_payload",
        ),
    )
    op.create_index("ix_messages_consultation_id", "messages", ["consultation_id"])

    op.create_table(
        "daily_missions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("mission_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("mission_type", sa.String(), nullable=False, server_default=sa.text("'walk'")),
        sa.Column("target_value", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("reward", sa.String(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pet_id", "mission_date", "mission_type", name="uq_mission_per_day"),
    )
    op.create_index("ix_daily_missions_pet_id", "daily_missions", ["pet_id"])

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("mission_id", sa.BigInteger(), nullable=True),
        sa.Column("source", activity_source, nullable=False,
                  server_default=sa.text("'phone'::activity_source")),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("duration_minutes", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("distance_meters", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("calories_burned", sa.Float(), nullable=True),
        sa.Column("avg_speed_kmh", sa.Float(), nullable=True),
        sa.Column("max_speed_kmh", sa.Float(), nullable=True),
        sa.Column("steps", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_mission_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["daily_missions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_logs_pet_id", "activity_logs", ["pet_id"])

    op.create_table(
        "vaccinations",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("vaccine_name", sa.String(), nullable=False),
        sa.Column("date_administered", sa.Date(), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("clinic_name", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vaccinations_pet_id", "vaccinations", ["pet_id"])
    op.create_index("ix_vaccinations_vaccine_name", "vaccinations", ["vaccine_name"])

    # Read-only reporting view (security_invoker so it respects the caller's
    # RLS/permissions rather than the definer's).
    op.execute(
        """
        CREATE OR REPLACE VIEW public.pet_history
        WITH (security_invoker = on) AS
        SELECT id, pet_id, 'assessment'::text AS event_type, created_at,
               risk_level::text AS detail, image_uri
        FROM health_assessments
        UNION ALL
        SELECT id, pet_id, 'activity'::text AS event_type, created_at,
               activity_type AS detail, NULL::text AS image_uri
        FROM activity_logs
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS public.pet_history")
    op.drop_table("vaccinations")
    op.drop_table("activity_logs")
    op.drop_table("daily_missions")
    op.drop_table("messages")
    op.drop_table("consultations")
    op.drop_table("health_assessments")
    op.drop_table("pet_profiles")
    op.drop_table("veterinarians")
    op.drop_table("users")

    bind = op.get_bind()
    activity_source.drop(bind, checkfirst=True)
    message_sender.drop(bind, checkfirst=True)
    consultation_status.drop(bind, checkfirst=True)
    risk_level.drop(bind, checkfirst=True)
