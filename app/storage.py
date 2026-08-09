"""User-scoped Supabase Storage clients and object naming helpers."""

from __future__ import annotations

import os
import uuid

from storage3 import SyncStorageClient, create_client as create_storage_client


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
STORAGE_TIMEOUT_SECONDS = int(os.getenv("SUPABASE_STORAGE_TIMEOUT_SECONDS", "20"))


class StorageConfigurationError(RuntimeError):
    """Raised when the Storage client cannot be configured safely."""


def create_user_storage_client(access_token: str) -> SyncStorageClient:
    """Create an isolated Storage client authenticated as the current user.

    A new client avoids shared mutable auth state between concurrent requests.
    The publishable key identifies the Supabase project; the verified user JWT
    in Authorization lets storage.objects RLS make the authorization decision.
    """

    if not SUPABASE_URL or not SUPABASE_KEY or not access_token:
        raise StorageConfigurationError("Supabase Storage is not configured")

    return create_storage_client(
        f"{SUPABASE_URL}/storage/v1",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        is_async=False,
        timeout=STORAGE_TIMEOUT_SECONDS,
    )


def assessment_object_path(
    supabase_uid: str,
    pet_id: int,
    extension: str,
) -> str:
    """Return an owner-scoped, collision-resistant object path."""

    return f"{supabase_uid}/{pet_id}/{uuid.uuid4().hex}{extension}"
