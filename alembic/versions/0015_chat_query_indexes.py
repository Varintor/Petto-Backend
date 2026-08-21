"""add indexes for the chat read path

Revision ID: 0015_chat_query_indexes
Revises: 0014_chat_realtime
Create Date: 2026-08-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0015_chat_query_indexes"
down_revision: Union[str, Sequence[str], None] = "0014_chat_realtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Match indexes to the ordered filters used while a chat is open."""
    op.create_index(
        "ix_messages_consultation_id_id",
        "messages",
        ["consultation_id", "id"],
    )
    op.create_index(
        "ix_appointments_consultation_starts_id",
        "appointments",
        ["consultation_id", "starts_at", "id"],
    )
    op.create_index(
        "ix_shared_health_cards_active_consultation_shared",
        "consultation_shared_health_cards",
        ["consultation_id", "shared_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shared_health_cards_active_consultation_shared",
        table_name="consultation_shared_health_cards",
    )
    op.drop_index(
        "ix_appointments_consultation_starts_id",
        table_name="appointments",
    )
    op.drop_index(
        "ix_messages_consultation_id_id",
        table_name="messages",
    )
