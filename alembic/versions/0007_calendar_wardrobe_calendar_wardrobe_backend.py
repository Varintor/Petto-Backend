"""calendar wardrobe backend

Revision ID: 0007_calendar_wardrobe
Revises: 0006_existing_table_rls
Create Date: 2026-08-11 18:45:55.222940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_calendar_wardrobe'
down_revision: Union[str, Sequence[str], None] = '0006_existing_table_rls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reminder_minutes", sa.Integer(), nullable=True, server_default=sa.text("30")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "event_type IN ('care', 'medication', 'vet', 'grooming', 'walk')",
            name="calendar_events_valid_type",
        ),
        sa.CheckConstraint(
            "reminder_minutes IS NULL OR reminder_minutes BETWEEN 0 AND 10080",
            name="calendar_events_valid_reminder",
        ),
    )
    op.create_index(
        "ix_calendar_events_pet_date",
        "calendar_events",
        ["pet_id", "event_date"],
    )

    op.create_table(
        "pet_wardrobe_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("pet_id", sa.BigInteger(), nullable=False),
        sa.Column("accessory_id", sa.String(length=64), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("equipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pet_id"], ["pet_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("pet_id", "accessory_id", name="uq_pet_wardrobe_item"),
    )
    op.create_index(
        "ix_pet_wardrobe_items_pet_id",
        "pet_wardrobe_items",
        ["pet_id"],
    )
    op.create_index(
        "uq_pet_wardrobe_one_equipped",
        "pet_wardrobe_items",
        ["pet_id"],
        unique=True,
        postgresql_where=sa.text("equipped_at IS NOT NULL"),
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in ("calendar_events", "pet_wardrobe_items"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon")
            op.execute(f"REVOKE ALL ON TABLE public.{table} FROM authenticated")
            op.execute(f"GRANT SELECT ON TABLE public.{table} TO authenticated")

        op.execute(
            """
            CREATE POLICY "calendar_events_select_owner" ON public.calendar_events
            FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1
                FROM public.pet_profiles p
                JOIN public.users u ON u.id = p.user_id
                WHERE p.id = calendar_events.pet_id
                  AND u.supabase_uid = (SELECT auth.uid())::text
            ))
            """
        )
        op.execute(
            """
            CREATE POLICY "pet_wardrobe_items_select_owner" ON public.pet_wardrobe_items
            FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1
                FROM public.pet_profiles p
                JOIN public.users u ON u.id = p.user_id
                WHERE p.id = pet_wardrobe_items.pet_id
                  AND u.supabase_uid = (SELECT auth.uid())::text
            ))
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            'DROP POLICY IF EXISTS "pet_wardrobe_items_select_owner" '
            "ON public.pet_wardrobe_items"
        )
        op.execute(
            'DROP POLICY IF EXISTS "calendar_events_select_owner" '
            "ON public.calendar_events"
        )
    op.drop_index("uq_pet_wardrobe_one_equipped", table_name="pet_wardrobe_items")
    op.drop_index("ix_pet_wardrobe_items_pet_id", table_name="pet_wardrobe_items")
    op.drop_table("pet_wardrobe_items")
    op.drop_index("ix_calendar_events_pet_date", table_name="calendar_events")
    op.drop_table("calendar_events")
