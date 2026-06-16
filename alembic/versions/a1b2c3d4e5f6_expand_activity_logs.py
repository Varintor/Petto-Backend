"""expand activity_logs with health-relevant columns

Revision ID: a1b2c3d4e5f6
Revises: d65684bb677a
Create Date: 2026-06-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd65684bb677a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('activity_logs', sa.Column('calories_burned', sa.Float(), nullable=True))
    op.add_column('activity_logs', sa.Column('avg_speed_kmh', sa.Float(), nullable=True))
    op.add_column('activity_logs', sa.Column('max_speed_kmh', sa.Float(), nullable=True))
    op.add_column('activity_logs', sa.Column('steps', sa.BigInteger(), nullable=True))
    op.add_column('activity_logs', sa.Column('route_polyline', sa.Text(), nullable=True))
    op.add_column('activity_logs', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('activity_logs', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('activity_logs', sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('activity_logs', 'ended_at')
    op.drop_column('activity_logs', 'started_at')
    op.drop_column('activity_logs', 'notes')
    op.drop_column('activity_logs', 'route_polyline')
    op.drop_column('activity_logs', 'steps')
    op.drop_column('activity_logs', 'max_speed_kmh')
    op.drop_column('activity_logs', 'avg_speed_kmh')
    op.drop_column('activity_logs', 'calories_burned')
