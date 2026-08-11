"""existing table rls

Revision ID: 0006_existing_table_rls
Revises: 0005_storage_owner_rls
Create Date: 2026-08-11 18:45:54.053660

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0006_existing_table_rls'
down_revision: Union[str, Sequence[str], None] = '0005_storage_owner_rls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Protect every existing public table before Realtime is enabled.

    FastAPI remains the only write path. Authenticated Supabase clients receive
    SELECT only, scoped to the owner or assigned consultation participant. This
    gives Postgres Changes the SELECT policy it needs without exposing direct
    client-side mutation APIs.
    """
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_activity_logs_mission_id "
        "ON public.activity_logs (mission_id)"
    )

    tables = (
        "users",
        "veterinarians",
        "pet_profiles",
        "health_assessments",
        "consultations",
        "messages",
        "daily_missions",
        "activity_logs",
        "vaccinations",
        "devices",
        "alembic_version",
    )
    for table in tables:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM anon")
        op.execute(f"REVOKE ALL ON TABLE public.{table} FROM authenticated")

    readable_tables = tuple(t for t in tables if t != "alembic_version")
    for table in readable_tables:
        op.execute(f"GRANT SELECT ON TABLE public.{table} TO authenticated")

    policy_names = {
        "users": ("users_select_self",),
        "veterinarians": ("veterinarians_select_self",),
        "pet_profiles": ("pet_profiles_select_owner",),
        "health_assessments": ("health_assessments_select_owner",),
        "consultations": ("consultations_select_participant",),
        "messages": ("messages_select_participant",),
        "daily_missions": ("daily_missions_select_owner",),
        "activity_logs": ("activity_logs_select_owner",),
        "vaccinations": ("vaccinations_select_owner",),
        "devices": ("devices_select_owner",),
    }
    for table, names in policy_names.items():
        for name in names:
            op.execute(f'DROP POLICY IF EXISTS "{name}" ON public.{table}')

    op.execute(
        """
        CREATE POLICY "users_select_self" ON public.users
        FOR SELECT TO authenticated
        USING (supabase_uid = (SELECT auth.uid())::text)
        """
    )
    op.execute(
        """
        CREATE POLICY "veterinarians_select_self" ON public.veterinarians
        FOR SELECT TO authenticated
        USING (supabase_uid = (SELECT auth.uid())::text)
        """
    )
    op.execute(
        """
        CREATE POLICY "pet_profiles_select_owner" ON public.pet_profiles
        FOR SELECT TO authenticated
        USING (EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = pet_profiles.user_id
              AND u.supabase_uid = (SELECT auth.uid())::text
        ))
        """
    )

    owner_scoped = (
        "health_assessments",
        "daily_missions",
        "activity_logs",
        "vaccinations",
        "devices",
    )
    for table in owner_scoped:
        op.execute(
            f"""
            CREATE POLICY "{table}_select_owner" ON public.{table}
            FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1
                FROM public.pet_profiles p
                JOIN public.users u ON u.id = p.user_id
                WHERE p.id = {table}.pet_id
                  AND u.supabase_uid = (SELECT auth.uid())::text
            ))
            """
        )

    op.execute(
        """
        CREATE POLICY "consultations_select_participant" ON public.consultations
        FOR SELECT TO authenticated
        USING (
            EXISTS (
                SELECT 1
                FROM public.pet_profiles p
                JOIN public.users u ON u.id = p.user_id
                WHERE p.id = consultations.pet_id
                  AND u.supabase_uid = (SELECT auth.uid())::text
            )
            OR EXISTS (
                SELECT 1 FROM public.veterinarians v
                WHERE v.id = consultations.vet_id
                  AND v.supabase_uid = (SELECT auth.uid())::text
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY "messages_select_participant" ON public.messages
        FOR SELECT TO authenticated
        USING (EXISTS (
            SELECT 1
            FROM public.consultations c
            LEFT JOIN public.pet_profiles p ON p.id = c.pet_id
            LEFT JOIN public.users u ON u.id = p.user_id
            LEFT JOIN public.veterinarians v ON v.id = c.vet_id
            WHERE c.id = messages.consultation_id
              AND (
                  u.supabase_uid = (SELECT auth.uid())::text
                  OR v.supabase_uid = (SELECT auth.uid())::text
              )
        ))
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    policy_names = {
        "users": "users_select_self",
        "veterinarians": "veterinarians_select_self",
        "pet_profiles": "pet_profiles_select_owner",
        "health_assessments": "health_assessments_select_owner",
        "consultations": "consultations_select_participant",
        "messages": "messages_select_participant",
        "daily_missions": "daily_missions_select_owner",
        "activity_logs": "activity_logs_select_owner",
        "vaccinations": "vaccinations_select_owner",
        "devices": "devices_select_owner",
    }
    for table, policy in policy_names.items():
        op.execute(f'DROP POLICY IF EXISTS "{policy}" ON public.{table}')

    for table in (*policy_names.keys(), "alembic_version"):
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP INDEX IF EXISTS public.ix_activity_logs_mission_id")
