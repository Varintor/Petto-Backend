"""schema validation indexes

Revision ID: 0011_schema_validation_indexes
Revises: 0010_private_storage
Create Date: 2026-08-11 19:05:09.883526

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011_schema_validation_indexes'
down_revision: Union[str, Sequence[str], None] = '0010_private_storage'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cover foreign keys and remove indexes duplicated by UNIQUE constraints."""
    op.create_index("ix_appointments_provider_id", "appointments", ["provider_id"])
    op.create_index(
        "ix_appointments_proposed_by_vet_id", "appointments", ["proposed_by_vet_id"]
    )
    op.create_index(
        "ix_consultation_shared_assessments_shared_by_user_id",
        "consultation_shared_assessments",
        ["shared_by_user_id"],
    )
    op.create_index(
        "ix_consultation_shared_health_cards_pet_id",
        "consultation_shared_health_cards",
        ["pet_id"],
    )
    op.create_index(
        "ix_consultation_shared_health_cards_shared_by_user_id",
        "consultation_shared_health_cards",
        ["shared_by_user_id"],
    )
    op.create_index("ix_consultations_assessment_id", "consultations", ["assessment_id"])

    if op.get_bind().dialect.name == "postgresql":
        for index_name in (
            "ix_users_email",
            "ix_users_supabase_uid",
            "ix_veterinarians_email",
            "ix_veterinarians_supabase_uid",
        ):
            op.execute(f"DROP INDEX IF EXISTS public.{index_name}")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.create_index("ix_veterinarians_supabase_uid", "veterinarians", ["supabase_uid"])
        op.create_index("ix_veterinarians_email", "veterinarians", ["email"])
        op.create_index("ix_users_supabase_uid", "users", ["supabase_uid"])
        op.create_index("ix_users_email", "users", ["email"])

    op.drop_index("ix_consultations_assessment_id", table_name="consultations")
    op.drop_index(
        "ix_consultation_shared_health_cards_shared_by_user_id",
        table_name="consultation_shared_health_cards",
    )
    op.drop_index(
        "ix_consultation_shared_health_cards_pet_id",
        table_name="consultation_shared_health_cards",
    )
    op.drop_index(
        "ix_consultation_shared_assessments_shared_by_user_id",
        table_name="consultation_shared_assessments",
    )
    op.drop_index("ix_appointments_proposed_by_vet_id", table_name="appointments")
    op.drop_index("ix_appointments_provider_id", table_name="appointments")
