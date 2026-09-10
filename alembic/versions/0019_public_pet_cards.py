"""public pet cards

Revision ID: 0019_public_pet_cards
Revises: 0018_tracking_vertical_slice
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_public_pet_cards"
down_revision = "0018_tracking_vertical_slice"
branch_labels = depends_on = None


def upgrade():
    op.create_table("public_pet_cards", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("pet_id", sa.BigInteger(), sa.ForeignKey("pet_profiles.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("token_hash", sa.String(64), nullable=False, unique=True), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")), sa.Column("visible_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")), sa.Column("contact_method", sa.String(255)), sa.Column("emergency_notes", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_public_pet_cards_pet_id", "public_pet_cards", ["pet_id"])
    op.create_index("ix_public_pet_cards_token_hash", "public_pet_cards", ["token_hash"])
    op.execute("ALTER TABLE public_pet_cards ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY public_pet_cards_owner_all ON public_pet_cards FOR ALL TO authenticated USING (EXISTS (SELECT 1 FROM pet_profiles p JOIN users u ON u.id=p.user_id WHERE p.id=public_pet_cards.pet_id AND u.supabase_uid=(SELECT auth.uid())::text)) WITH CHECK (EXISTS (SELECT 1 FROM pet_profiles p JOIN users u ON u.id=p.user_id WHERE p.id=public_pet_cards.pet_id AND u.supabase_uid=(SELECT auth.uid())::text))")


def downgrade():
    op.drop_table("public_pet_cards")
