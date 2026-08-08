"""Add explicit AI assessment completion/failure state.

Revision ID: 0004_assessment_failure_status
Revises: 0003_feature3_5_device_tracking
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_assessment_failure_status"
down_revision: Union[str, Sequence[str], None] = "0003_feature3_5_device_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "health_assessments",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="completed",
        ),
    )
    op.add_column(
        "health_assessments",
        sa.Column("error_code", sa.String(length=50), nullable=True),
    )
    op.create_check_constraint(
        "health_assessments_valid_status",
        "health_assessments",
        "status IN ('completed', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "health_assessments_valid_status",
        "health_assessments",
        type_="check",
    )
    op.drop_column("health_assessments", "error_code")
    op.drop_column("health_assessments", "status")
