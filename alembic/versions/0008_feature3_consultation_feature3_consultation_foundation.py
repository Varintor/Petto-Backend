"""feature3 consultation foundation

Revision ID: 0008_feature3_consultation
Revises: 0007_calendar_wardrobe
Create Date: 2026-08-11 18:45:56.568265

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008_feature3_consultation'
down_revision: Union[str, Sequence[str], None] = '0007_calendar_wardrobe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "veterinarians",
        sa.Column(
            "verification_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )
    op.add_column(
        "veterinarians",
        sa.Column(
            "is_accepting_consultations",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "veterinarians",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_check_constraint(
        "veterinarians_valid_verification_status",
        "veterinarians",
        "verification_status IN ('pending', 'approved', 'rejected', 'disabled')",
    )

    op.create_table(
        "veterinary_providers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("external_place_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provider_type", sa.String(length=30), nullable=False, server_default=sa.text("'hospital'")),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("operating_hours", sa.JSON(), nullable=True),
        sa.Column("provider_status", sa.String(length=20), nullable=False, server_default=sa.text("'listed'")),
        sa.Column("consultation_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("external_place_id", name="uq_veterinary_providers_external_place_id"),
        sa.CheckConstraint(
            "provider_type IN ('hospital', 'clinic', 'independent')",
            name="veterinary_providers_valid_type",
        ),
        sa.CheckConstraint(
            "provider_status IN ('listed', 'partner', 'disabled')",
            name="veterinary_providers_valid_status",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="veterinary_providers_valid_latitude",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="veterinary_providers_valid_longitude",
        ),
    )
    op.create_index(
        "ix_veterinary_providers_location",
        "veterinary_providers",
        ["latitude", "longitude"],
    )

    op.create_table(
        "provider_veterinarians",
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("veterinarian_id", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("accepting_consultations", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["provider_id"], ["veterinary_providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["veterinarian_id"], ["veterinarians.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("provider_id", "veterinarian_id"),
    )
    op.create_index(
        "ix_provider_veterinarians_veterinarian_id",
        "provider_veterinarians",
        ["veterinarian_id"],
    )

    op.add_column("consultations", sa.Column("provider_id", sa.BigInteger(), nullable=True))
    op.add_column("consultations", sa.Column("subject", sa.String(length=200), nullable=True))
    op.add_column("consultations", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_consultations_provider_id",
        "consultations",
        "veterinary_providers",
        ["provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_consultations_provider_id", "consultations", ["provider_id"])
    op.create_index(
        "ix_consultations_status_updated",
        "consultations",
        ["status", "updated_at"],
    )

    op.add_column(
        "messages",
        sa.Column(
            "client_message_id",
            sa.Uuid(),
            nullable=True,
            server_default=sa.text("gen_random_uuid()") if op.get_bind().dialect.name == "postgresql" else None,
        ),
    )
    op.add_column(
        "messages",
        sa.Column("message_type", sa.String(length=20), nullable=False, server_default=sa.text("'text'")),
    )
    op.add_column("messages", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "messages_valid_message_type",
        "messages",
        "message_type IN ('text', 'assessment', 'appointment', 'system', 'ai')",
    )
    op.create_unique_constraint(
        "uq_messages_consultation_client_id",
        "messages",
        ["consultation_id", "client_message_id"],
    )
    op.create_index(
        "ix_messages_consultation_created",
        "messages",
        ["consultation_id", "created_at"],
    )

    op.create_table(
        "consultation_shared_assessments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("consultation_id", sa.BigInteger(), nullable=False),
        sa.Column("assessment_id", sa.BigInteger(), nullable=False),
        sa.Column("shared_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_id"], ["health_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("consultation_id", "assessment_id", name="uq_consultation_shared_assessment"),
    )
    op.create_index(
        "ix_shared_assessments_assessment_id",
        "consultation_shared_assessments",
        ["assessment_id"],
    )

    # Preserve assessment shares created by the older one-assessment-per-chat model.
    op.execute(
        """
        INSERT INTO consultation_shared_assessments
            (consultation_id, assessment_id, shared_by_user_id, shared_at)
        SELECT c.id, c.assessment_id, p.user_id, c.created_at
        FROM consultations c
        JOIN pet_profiles p ON p.id = c.pet_id
        WHERE c.assessment_id IS NOT NULL
        ON CONFLICT (consultation_id, assessment_id) DO NOTHING
        """
    )

    op.create_table(
        "appointments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("consultation_id", sa.BigInteger(), nullable=False),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=True),
        sa.Column("proposed_by_vet_id", sa.BigInteger(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'proposed'")),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["veterinary_providers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["proposed_by_vet_id"], ["veterinarians.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'declined', 'cancelled', 'completed')",
            name="appointments_valid_status",
        ),
        sa.CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="appointments_valid_time_range"),
    )
    op.create_index("ix_appointments_pet_starts", "appointments", ["pet_id", "starts_at"])
    op.create_index("ix_appointments_consultation", "appointments", ["consultation_id"])

    op.add_column("calendar_events", sa.Column("appointment_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_calendar_events_appointment_id",
        "calendar_events",
        "appointments",
        ["appointment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_calendar_events_appointment_id",
        "calendar_events",
        ["appointment_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "veterinary_providers",
            "provider_veterinarians",
            "consultation_shared_assessments",
            "appointments",
        ):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM authenticated")
            op.execute(f"GRANT SELECT ON TABLE public.{table} TO authenticated")

        op.execute(
            """
            CREATE POLICY "veterinary_providers_select_listed"
            ON public.veterinary_providers FOR SELECT TO authenticated
            USING (provider_status <> 'disabled')
            """
        )
        op.execute(
            """
            CREATE POLICY "provider_veterinarians_select_active"
            ON public.provider_veterinarians FOR SELECT TO authenticated
            USING (is_active)
            """
        )
        for table in ("consultation_shared_assessments", "appointments"):
            op.execute(
                f"""
                CREATE POLICY "{table}_select_participant" ON public.{table}
                FOR SELECT TO authenticated
                USING (EXISTS (
                    SELECT 1
                    FROM public.consultations c
                    LEFT JOIN public.pet_profiles p ON p.id = c.pet_id
                    LEFT JOIN public.users u ON u.id = p.user_id
                    LEFT JOIN public.veterinarians v ON v.id = c.vet_id
                    WHERE c.id = {table}.consultation_id
                      AND (
                          u.supabase_uid = (SELECT auth.uid())::text
                          OR v.supabase_uid = (SELECT auth.uid())::text
                      )
                ))
                """
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table, policy in (
            ("appointments", "appointments_select_participant"),
            (
                "consultation_shared_assessments",
                "consultation_shared_assessments_select_participant",
            ),
            ("provider_veterinarians", "provider_veterinarians_select_active"),
            ("veterinary_providers", "veterinary_providers_select_listed"),
        ):
            op.execute(f'DROP POLICY IF EXISTS "{policy}" ON public.{table}')

    op.drop_constraint("uq_calendar_events_appointment_id", "calendar_events", type_="unique")
    op.drop_constraint("fk_calendar_events_appointment_id", "calendar_events", type_="foreignkey")
    op.drop_column("calendar_events", "appointment_id")
    op.drop_index("ix_appointments_consultation", table_name="appointments")
    op.drop_index("ix_appointments_pet_starts", table_name="appointments")
    op.drop_table("appointments")
    op.drop_index("ix_shared_assessments_assessment_id", table_name="consultation_shared_assessments")
    op.drop_table("consultation_shared_assessments")
    op.drop_index("ix_messages_consultation_created", table_name="messages")
    op.drop_constraint("uq_messages_consultation_client_id", "messages", type_="unique")
    op.drop_constraint("messages_valid_message_type", "messages", type_="check")
    op.drop_column("messages", "read_at")
    op.drop_column("messages", "delivered_at")
    op.drop_column("messages", "message_type")
    op.drop_column("messages", "client_message_id")
    op.drop_index("ix_consultations_status_updated", table_name="consultations")
    op.drop_index("ix_consultations_provider_id", table_name="consultations")
    op.drop_constraint("fk_consultations_provider_id", "consultations", type_="foreignkey")
    op.drop_column("consultations", "closed_at")
    op.drop_column("consultations", "subject")
    op.drop_column("consultations", "provider_id")
    op.drop_index("ix_provider_veterinarians_veterinarian_id", table_name="provider_veterinarians")
    op.drop_table("provider_veterinarians")
    op.drop_index("ix_veterinary_providers_location", table_name="veterinary_providers")
    op.drop_table("veterinary_providers")
    op.drop_constraint(
        "veterinarians_valid_verification_status",
        "veterinarians",
        type_="check",
    )
    op.drop_column("veterinarians", "updated_at")
    op.drop_column("veterinarians", "is_accepting_consultations")
    op.drop_column("veterinarians", "verification_status")
