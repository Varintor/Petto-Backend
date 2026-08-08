# -*- coding: utf-8 -*-
"""Feature 3/5 + multi-device tracking groundwork.

- devices: paired BLE/GPS collars per pet (latest position only, no route -
  proposal privacy rule).
- consultations.assessment_id: links a forwarded AI assessment (UD-06).
- message_sender enum gains 'ai' for server-generated AI-assist summaries.

Revision ID: 0003_feature3_5_device_tracking
Revises: 0002_add_pet_blood_type
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_feature3_5_device_tracking"
down_revision: Union[str, Sequence[str], None] = "0002_add_pet_blood_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("device_type", sa.String(), nullable=False, server_default=sa.text("'ble_collar'")),
        sa.Column("identifier", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("battery_percent", sa.Integer(), nullable=True),
        sa.Column("last_lat", sa.Float(), nullable=True),
        sa.Column("last_lng", sa.Float(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paired_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("identifier", name="uq_devices_identifier"),
    )
    op.create_index("ix_devices_pet_id", "devices", ["pet_id"])

    op.add_column(
        "consultations",
        sa.Column("assessment_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_consultations_assessment_id",
        "consultations", "health_assessments",
        ["assessment_id"], ["id"], ondelete="SET NULL",
    )

    # Postgres enum: add the 'ai' sender label (no-op on SQLite test DBs).
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE message_sender ADD VALUE IF NOT EXISTS 'ai'")


def downgrade() -> None:
    op.drop_constraint("fk_consultations_assessment_id", "consultations", type_="foreignkey")
    op.drop_column("consultations", "assessment_id")
    op.drop_index("ix_devices_pet_id", table_name="devices")
    op.drop_table("devices")
    # NOTE: Postgres cannot drop a single enum value; 'ai' label stays.
