"""Authorize owner-scoped assessment uploads in Supabase Storage.

Revision ID: 0005_storage_owner_rls
Revises: 0004_assessment_failure_status
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0005_storage_owner_rls"
down_revision: Union[str, Sequence[str], None] = "0004_assessment_failure_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INSERT_POLICY = "pet_images_insert_in_own_folder"
SELECT_POLICY = "pet_images_select_own_objects"


def upgrade() -> None:
    # Supabase assigns storage.objects.owner_id from the JWT subject. Object
    # paths start with that same subject, followed by the pet id. The API still
    # performs the authoritative pet ownership check before attempting upload.
    op.execute(
        f'DROP POLICY IF EXISTS "{INSERT_POLICY}" ON storage.objects'
    )
    op.execute(
        f'DROP POLICY IF EXISTS "{SELECT_POLICY}" ON storage.objects'
    )
    op.execute(
        f"""
        CREATE POLICY "{INSERT_POLICY}"
        ON storage.objects
        FOR INSERT
        TO authenticated
        WITH CHECK (
            bucket_id = 'pet-images'
            AND (storage.foldername(name))[1] = (SELECT auth.uid()::text)
        )
        """
    )
    # Storage upload returns the inserted metadata row. A matching SELECT
    # policy is therefore required even though the bucket currently serves
    # public downloads.
    op.execute(
        f"""
        CREATE POLICY "{SELECT_POLICY}"
        ON storage.objects
        FOR SELECT
        TO authenticated
        USING (
            bucket_id = 'pet-images'
            AND owner_id = (SELECT auth.uid()::text)
        )
        """
    )


def downgrade() -> None:
    op.execute(
        f'DROP POLICY IF EXISTS "{SELECT_POLICY}" ON storage.objects'
    )
    op.execute(
        f'DROP POLICY IF EXISTS "{INSERT_POLICY}" ON storage.objects'
    )
