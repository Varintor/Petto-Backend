"""publish consultation state changes to realtime

Revision ID: 0016_consultation_realtime
Revises: 0015_chat_query_indexes
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0016_consultation_realtime"
down_revision: Union[str, Sequence[str], None] = "0015_chat_query_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REALTIME_TABLES = (
    "appointments",
    "consultation_shared_assessments",
    "consultation_shared_health_cards",
)


def upgrade() -> None:
    """Publish participant-protected consultation state to Realtime."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name in REALTIME_TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_publication_tables
                    WHERE pubname = 'supabase_realtime'
                      AND schemaname = 'public'
                      AND tablename = '{table_name}'
                ) THEN
                    ALTER PUBLICATION supabase_realtime
                    ADD TABLE public.{table_name};
                END IF;
            END
            $$
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name in reversed(REALTIME_TABLES):
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_publication_tables
                    WHERE pubname = 'supabase_realtime'
                      AND schemaname = 'public'
                      AND tablename = '{table_name}'
                ) THEN
                    ALTER PUBLICATION supabase_realtime
                    DROP TABLE public.{table_name};
                END IF;
            END
            $$
            """
        )
