"""tracking state, persistent alerts and idempotent sessions

Revision ID: 0018_tracking_vertical_slice
Revises: 0017_urgent_consultations
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_tracking_vertical_slice"
down_revision = "0017_urgent_consultations"
branch_labels = depends_on = None


def upgrade():
    op.add_column("devices", sa.Column("last_speed_kmh", sa.Float()))
    op.add_column("devices", sa.Column("last_accuracy_m", sa.Float()))
    op.add_column("devices", sa.Column("last_moved_at", sa.DateTime(timezone=True)))
    op.add_column("devices", sa.Column("motion_state", sa.String(20), nullable=False, server_default="unknown"))
    op.add_column("devices", sa.Column("high_speed_started_at", sa.DateTime(timezone=True)))
    op.add_column("devices", sa.Column("high_speed_sample_count", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("devices_valid_motion_state", "devices", "motion_state IN ('moving','stationary','offline','unknown')")
    op.add_column("activity_logs", sa.Column("session_key", sa.String(120)))
    op.create_unique_constraint("uq_activity_pet_session_key", "activity_logs", ["pet_id", "session_key"])
    op.create_table("device_alerts", sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("device_id", sa.BigInteger(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False), sa.Column("alert_type", sa.String(40), nullable=False), sa.Column("severity", sa.String(20), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("acknowledged_at", sa.DateTime(timezone=True)), sa.Column("resolved_at", sa.DateTime(timezone=True)), sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")), sa.CheckConstraint("alert_type IN ('device_offline','prolonged_inactivity','sustained_high_speed','low_battery')", name="device_alerts_valid_type"))
    op.create_index("ix_device_alerts_device_id", "device_alerts", ["device_id"])
    op.create_index("uq_device_alerts_active_type", "device_alerts", ["device_id", "alert_type"], unique=True, postgresql_where=sa.text("resolved_at IS NULL"))
    op.execute("ALTER TABLE device_alerts ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY device_alerts_owner_select ON device_alerts FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM devices d JOIN pet_profiles p ON p.id=d.pet_id JOIN users u ON u.id=p.user_id WHERE d.id=device_alerts.device_id AND u.supabase_uid=(SELECT auth.uid())::text))")
    for table_name in ("devices", "device_alerts"):
        op.execute(sa.text(f"""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_publication_tables WHERE pubname='supabase_realtime' AND schemaname='public' AND tablename='{table_name}') THEN ALTER PUBLICATION supabase_realtime ADD TABLE public.{table_name}; END IF; END $$;"""))


def downgrade():
    op.execute("ALTER PUBLICATION supabase_realtime DROP TABLE device_alerts")
    op.drop_table("device_alerts"); op.drop_constraint("uq_activity_pet_session_key", "activity_logs", type_="unique"); op.drop_column("activity_logs", "session_key")
    op.drop_constraint("devices_valid_motion_state", "devices", type_="check")
    for c in ("high_speed_sample_count","high_speed_started_at","motion_state","last_moved_at","last_accuracy_m","last_speed_kmh"): op.drop_column("devices", c)
