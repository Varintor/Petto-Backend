"""private assessment storage

Revision ID: 0010_private_storage
Revises: 0009_feature5_health_profile
Create Date: 2026-08-11 18:45:59.786726

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0010_private_storage'
down_revision: Union[str, Sequence[str], None] = '0009_feature5_health_profile'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # Keep the database and API limits aligned: JPEG/PNG/WebP up to 10 MiB.
    op.execute(
        """
        UPDATE storage.buckets
        SET public = false,
            file_size_limit = 10485760,
            allowed_mime_types = ARRAY['image/jpeg', 'image/png', 'image/webp']::text[]
        WHERE id = 'pet-images'
        """
    )

    for policy in (
        "Allow public uploads x0itpi_0",
        "pet_images_insert_in_own_folder",
        "pet_images_select_own_objects",
        "pet_images_update_own_objects",
        "pet_images_delete_own_objects",
        "pet_images_select_shared_with_vet",
    ):
        escaped = policy.replace('"', '""')
        op.execute(f'DROP POLICY IF EXISTS "{escaped}" ON storage.objects')

    op.execute(
        """
        CREATE POLICY "pet_images_insert_in_own_folder"
        ON storage.objects FOR INSERT TO authenticated
        WITH CHECK (
            bucket_id = 'pet-images'
            AND (storage.foldername(name))[1] = (SELECT auth.uid())::text
        )
        """
    )
    op.execute(
        """
        CREATE POLICY "pet_images_select_own_objects"
        ON storage.objects FOR SELECT TO authenticated
        USING (
            bucket_id = 'pet-images'
            AND owner_id = (SELECT auth.uid())::text
        )
        """
    )
    op.execute(
        """
        CREATE POLICY "pet_images_update_own_objects"
        ON storage.objects FOR UPDATE TO authenticated
        USING (
            bucket_id = 'pet-images'
            AND owner_id = (SELECT auth.uid())::text
        )
        WITH CHECK (
            bucket_id = 'pet-images'
            AND owner_id = (SELECT auth.uid())::text
            AND (storage.foldername(name))[1] = (SELECT auth.uid())::text
        )
        """
    )
    op.execute(
        """
        CREATE POLICY "pet_images_delete_own_objects"
        ON storage.objects FOR DELETE TO authenticated
        USING (
            bucket_id = 'pet-images'
            AND owner_id = (SELECT auth.uid())::text
        )
        """
    )
    op.execute(
        """
        CREATE POLICY "pet_images_select_shared_with_vet"
        ON storage.objects FOR SELECT TO authenticated
        USING (
            bucket_id = 'pet-images'
            AND EXISTS (
                SELECT 1
                FROM public.health_assessments a
                JOIN public.consultation_shared_assessments s
                  ON s.assessment_id = a.id AND s.revoked_at IS NULL
                JOIN public.consultations c ON c.id = s.consultation_id
                JOIN public.veterinarians v ON v.id = c.vet_id
                WHERE v.supabase_uid = (SELECT auth.uid())::text
                  AND (
                      a.image_uri = storage.objects.name
                      OR a.image_uri LIKE ('%/pet-images/' || storage.objects.name)
                  )
            )
        )
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for policy in (
        "pet_images_select_shared_with_vet",
        "pet_images_delete_own_objects",
        "pet_images_update_own_objects",
        "pet_images_select_own_objects",
        "pet_images_insert_in_own_folder",
    ):
        op.execute(f'DROP POLICY IF EXISTS "{policy}" ON storage.objects')

    op.execute(
        """
        UPDATE storage.buckets
        SET public = true,
            file_size_limit = NULL,
            allowed_mime_types = NULL
        WHERE id = 'pet-images'
        """
    )
