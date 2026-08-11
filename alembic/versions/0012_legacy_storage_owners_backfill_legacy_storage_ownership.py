"""backfill legacy storage ownership

Revision ID: 0012_legacy_storage_owners
Revises: 0011_schema_validation_indexes
Create Date: 2026-08-11 19:13:08.392820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012_legacy_storage_owners'
down_revision: Union[str, Sequence[str], None] = '0011_schema_validation_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # Uploads made before owner-scoped Storage RLS have owner_id=NULL and use
    # flat legacy object names. Recover ownership only when the database can
    # prove a single owner through assessment -> pet -> user. Orphaned files
    # deliberately remain inaccessible in the private bucket.
    op.execute(
        """
        WITH resolved_owners AS (
            SELECT o.id AS object_id, min(u.supabase_uid) AS supabase_uid
            FROM storage.objects o
            JOIN public.health_assessments a
              ON a.image_uri = o.name
              OR a.image_uri LIKE ('%/pet-images/' || o.name)
            JOIN public.pet_profiles p ON p.id = a.pet_id
            JOIN public.users u ON u.id = p.user_id
            WHERE o.bucket_id = 'pet-images'
              AND o.owner_id IS NULL
              AND u.supabase_uid IS NOT NULL
            GROUP BY o.id
            HAVING count(DISTINCT u.supabase_uid) = 1
        )
        UPDATE storage.objects o
        SET owner_id = r.supabase_uid
        FROM resolved_owners r
        WHERE o.id = r.object_id
        """
    )


def downgrade() -> None:
    # Ownership repair is intentionally retained. Clearing it during an app
    # rollback would make legitimate legacy images inaccessible again.
    pass
