"""publish veterinarian consultation inbox changes to realtime

Revision ID: 0020_vet_inbox_realtime
Revises: 0019_public_pet_cards
"""

from alembic import op


revision = "0020_vet_inbox_realtime"
down_revision = "0019_public_pet_cards"
branch_labels = depends_on = None


def upgrade() -> None:
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
                  AND tablename = 'consultations'
            ) THEN
                ALTER PUBLICATION supabase_realtime
                ADD TABLE public.consultations;
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
                  AND tablename = 'consultations'
            ) THEN
                ALTER PUBLICATION supabase_realtime
                DROP TABLE public.consultations;
            END IF;
        END
        $$
        """
    )
