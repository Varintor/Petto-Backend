"""bounded device telemetry history

Revision ID: 0021_device_telemetry
Revises: 0020_vet_inbox_realtime
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_device_telemetry"
down_revision = "0020_vet_inbox_realtime"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "device_telemetry_points",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "device_id",
            sa.BigInteger(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("speed_kmh", sa.Float()),
        sa.Column("accuracy_m", sa.Float()),
        sa.Column("motion_state", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "motion_state IN ('moving','stationary','offline','unknown')",
            name="telemetry_valid_motion_state",
        ),
    )
    op.create_index(
        "ix_telemetry_device_recorded",
        "device_telemetry_points",
        ["device_id", "recorded_at"],
    )

    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE public.device_telemetry_points ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.device_telemetry_points FROM anon")
    op.execute("REVOKE ALL ON TABLE public.device_telemetry_points FROM authenticated")
    op.execute("GRANT SELECT ON TABLE public.device_telemetry_points TO authenticated")
    op.execute(
        """
        CREATE POLICY "telemetry_select_owner"
        ON public.device_telemetry_points
        FOR SELECT TO authenticated
        USING (EXISTS (
            SELECT 1
            FROM public.devices d
            JOIN public.pet_profiles p ON p.id = d.pet_id
            JOIN public.users u ON u.id = p.user_id
            WHERE d.id = device_telemetry_points.device_id
              AND u.supabase_uid = (SELECT auth.uid())::text
        ))
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_publication_tables
            WHERE pubname='supabase_realtime'
              AND schemaname='public'
              AND tablename='device_telemetry_points'
          ) THEN
            ALTER PUBLICATION supabase_realtime
              ADD TABLE public.device_telemetry_points;
          END IF;
        END $$;
        """
    )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER PUBLICATION supabase_realtime "
            "DROP TABLE public.device_telemetry_points"
        )
    op.drop_index("ix_telemetry_device_recorded", table_name="device_telemetry_points")
    op.drop_table("device_telemetry_points")
