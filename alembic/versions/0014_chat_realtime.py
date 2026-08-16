"""enable chat realtime

Revision ID: 0014_chat_realtime
Revises: 0013_wardrobe_reward_ids
Create Date: 2026-08-16
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0014_chat_realtime"
down_revision: Union[str, Sequence[str], None] = "0013_wardrobe_reward_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Publish participant-protected chat rows to Supabase Realtime."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_publication_tables
                WHERE pubname = 'supabase_realtime'
                  AND schemaname = 'public'
                  AND tablename = 'messages'
            ) THEN
                ALTER PUBLICATION supabase_realtime ADD TABLE public.messages;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_publication_tables
                WHERE pubname = 'supabase_realtime'
                  AND schemaname = 'public'
                  AND tablename = 'messages'
            ) THEN
                ALTER PUBLICATION supabase_realtime DROP TABLE public.messages;
            END IF;
        END
        $$
        """
    )
