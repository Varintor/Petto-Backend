"""feature5 health profile

Revision ID: 0009_feature5_health_profile
Revises: 0008_feature3_consultation
Create Date: 2026-08-11 18:45:58.192692

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0009_feature5_health_profile'
down_revision: Union[str, Sequence[str], None] = '0008_feature3_consultation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = (
        postgresql.JSONB(astext_type=sa.Text())
        if op.get_bind().dialect.name == "postgresql"
        else sa.JSON()
    )
    empty_array_default = sa.text("'[]'::jsonb") if op.get_bind().dialect.name == "postgresql" else None

    op.create_table(
        "pet_health_profiles",
        sa.Column("pet_id", sa.BigInteger(), primary_key=True),
        sa.Column("allergies", json_type, nullable=False, server_default=empty_array_default),
        sa.Column("chronic_conditions", json_type, nullable=False, server_default=empty_array_default),
        sa.Column("current_medications", json_type, nullable=False, server_default=empty_array_default),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "pet_health_profiles_allergies_array",
            "pet_health_profiles",
            "jsonb_typeof(allergies) = 'array'",
        )
        op.create_check_constraint(
            "pet_health_profiles_conditions_array",
            "pet_health_profiles",
            "jsonb_typeof(chronic_conditions) = 'array'",
        )
        op.create_check_constraint(
            "pet_health_profiles_medications_array",
            "pet_health_profiles",
            "jsonb_typeof(current_medications) = 'array'",
        )

    op.create_table(
        "consultation_shared_health_cards",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("consultation_id", sa.BigInteger(), nullable=False),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("shared_by_user_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot", json_type, nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["consultation_id"], ["consultations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shared_by_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_shared_health_cards_consultation",
        "consultation_shared_health_cards",
        ["consultation_id", "shared_at"],
    )

    op.create_index(
        "ix_assessments_pet_created",
        "health_assessments",
        ["pet_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_activity_logs_pet_created",
        "activity_logs",
        ["pet_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_vaccinations_pet_created",
        "vaccinations",
        ["pet_id", sa.text("created_at DESC")],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE VIEW public.pet_history
            WITH (security_invoker = on) AS
            SELECT id, pet_id, 'assessment'::text AS event_type, created_at,
                   COALESCE(risk_level::text, status) AS detail, image_uri
            FROM public.health_assessments
            UNION ALL
            SELECT id, pet_id, 'activity'::text AS event_type, created_at,
                   activity_type AS detail, NULL::text AS image_uri
            FROM public.activity_logs
            UNION ALL
            SELECT id, pet_id, 'vaccination'::text AS event_type, created_at,
                   vaccine_name AS detail, NULL::text AS image_uri
            FROM public.vaccinations
            UNION ALL
            SELECT id, pet_id, 'mission'::text AS event_type, completed_at AS created_at,
                   title AS detail, NULL::text AS image_uri
            FROM public.daily_missions
            WHERE is_completed AND completed_at IS NOT NULL
            UNION ALL
            SELECT id, pet_id, 'appointment'::text AS event_type, starts_at AS created_at,
                   COALESCE(reason, 'Veterinary appointment') AS detail,
                   NULL::text AS image_uri
            FROM public.appointments
            WHERE status IN ('accepted', 'completed')
            """
        )
        op.execute("REVOKE ALL ON TABLE public.pet_history FROM anon")
        op.execute("REVOKE ALL ON TABLE public.pet_history FROM authenticated")
        op.execute("GRANT SELECT ON TABLE public.pet_history TO authenticated")

        for table in ("pet_health_profiles", "consultation_shared_health_cards"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM authenticated")
            op.execute(f"GRANT SELECT ON TABLE public.{table} TO authenticated")

        op.execute(
            """
            CREATE POLICY "pet_health_profiles_select_owner" ON public.pet_health_profiles
            FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1
                FROM public.pet_profiles p
                JOIN public.users u ON u.id = p.user_id
                WHERE p.id = pet_health_profiles.pet_id
                  AND u.supabase_uid = (SELECT auth.uid())::text
            ))
            """
        )
        op.execute(
            """
            CREATE POLICY "shared_health_cards_select_participant"
            ON public.consultation_shared_health_cards
            FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1
                FROM public.consultations c
                LEFT JOIN public.pet_profiles p ON p.id = c.pet_id
                LEFT JOIN public.users u ON u.id = p.user_id
                LEFT JOIN public.veterinarians v ON v.id = c.vet_id
                WHERE c.id = consultation_shared_health_cards.consultation_id
                  AND (
                      u.supabase_uid = (SELECT auth.uid())::text
                      OR v.supabase_uid = (SELECT auth.uid())::text
                  )
            ))
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            'DROP POLICY IF EXISTS "shared_health_cards_select_participant" '
            "ON public.consultation_shared_health_cards"
        )
        op.execute(
            'DROP POLICY IF EXISTS "pet_health_profiles_select_owner" '
            "ON public.pet_health_profiles"
        )
        op.execute(
            """
            CREATE OR REPLACE VIEW public.pet_history
            WITH (security_invoker = on) AS
            SELECT id, pet_id, 'assessment'::text AS event_type, created_at,
                   risk_level::text AS detail, image_uri
            FROM public.health_assessments
            UNION ALL
            SELECT id, pet_id, 'activity'::text AS event_type, created_at,
                   activity_type AS detail, NULL::text AS image_uri
            FROM public.activity_logs
            """
        )

    op.drop_index("ix_vaccinations_pet_created", table_name="vaccinations")
    op.drop_index("ix_activity_logs_pet_created", table_name="activity_logs")
    op.drop_index("ix_assessments_pet_created", table_name="health_assessments")
    op.drop_index("ix_shared_health_cards_consultation", table_name="consultation_shared_health_cards")
    op.drop_table("consultation_shared_health_cards")
    op.drop_table("pet_health_profiles")
