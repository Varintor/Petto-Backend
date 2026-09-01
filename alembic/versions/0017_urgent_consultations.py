"""add explicit priority for urgent consultations

Revision ID: 0017_urgent_consultations
Revises: 0016_consultation_realtime
Create Date: 2026-08-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_urgent_consultations"
down_revision: Union[str, Sequence[str], None] = "0016_consultation_realtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "consultations",
        sa.Column(
            "priority",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'normal'"),
        ),
    )
    op.create_check_constraint(
        "consultations_valid_priority",
        "consultations",
        "priority IN ('normal', 'urgent')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "consultations_valid_priority",
        "consultations",
        type_="check",
    )
    op.drop_column("consultations", "priority")
