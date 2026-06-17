"""drop activity_logs.route_polyline + veterinarians supabase auth migration

- Drop activity_logs.route_polyline (privacy: Petto proposal §3.7 — raw GPS is
  on-device only, never persisted).
- Bridge veterinarians to Supabase Auth: add supabase_uid (unique, nullable)
  and relax password_hash to nullable so legacy/migrated rows can sit without
  a hashed password. password_hash stays for backwards compatibility with any
  vet account created before the Supabase Auth flow lands.

Revision ID: e3f1a2b4c5d6
Revises: f7a8b9c0d1e2
Create Date: 2026-06-17 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f1a2b4c5d6'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Privacy: drop raw GPS column from activity_logs
    op.drop_column('activity_logs', 'route_polyline')

    # 2. Veterinarians: bridge to Supabase Auth
    op.add_column(
        'veterinarians',
        sa.Column('supabase_uid', sa.String(), nullable=True),
    )
    op.create_index(
        'ix_veterinarians_supabase_uid',
        'veterinarians',
        ['supabase_uid'],
        unique=True,
    )
    # Existing rows have a non-null password_hash; new Supabase-Auth rows will
    # have it NULL. Relax the column to permit that.
    op.alter_column(
        'veterinarians',
        'password_hash',
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    # Reverse veterinarian changes
    op.alter_column(
        'veterinarians',
        'password_hash',
        existing_type=sa.String(),
        nullable=False,
    )
    op.drop_index('ix_veterinarians_supabase_uid', table_name='veterinarians')
    op.drop_column('veterinarians', 'supabase_uid')

    # Restore raw GPS column (kept for reversibility; not used by the app)
    op.add_column(
        'activity_logs',
        sa.Column('route_polyline', sa.Text(), nullable=True),
    )
