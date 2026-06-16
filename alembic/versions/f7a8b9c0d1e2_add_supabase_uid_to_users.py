"""add supabase_uid to users

Revision ID: f7a8b9c0d1e2
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("supabase_uid", sa.String(), nullable=True))
    op.create_index("ix_users_supabase_uid", "users", ["supabase_uid"], unique=True)
    op.alter_column("users", "password_hash", nullable=True)


def downgrade() -> None:
    op.alter_column("users", "password_hash", nullable=False)
    op.drop_index("ix_users_supabase_uid", table_name="users")
    op.drop_column("users", "supabase_uid")
