# -*- coding: utf-8 -*-
"""Add pet_profiles.blood_type.

The Flutter pet form has collected a blood type (A/B/AB/O) since the add-pet
redesign, but the column never existed server-side, so Pydantic silently
dropped the value. This migration persists it.

Revision ID: 0002_add_pet_blood_type
Revises: 0001_baseline_schema
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_pet_blood_type"
down_revision: Union[str, Sequence[str], None] = "0001_baseline_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pet_profiles", sa.Column("blood_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("pet_profiles", "blood_type")
