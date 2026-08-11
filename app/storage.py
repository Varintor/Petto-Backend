"""User-scoped Supabase Storage clients and object naming helpers."""

from __future__ import annotations

import os
import uuid
from urllib.parse import unquote, urlparse

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


def storage_object_path(image_uri: str | None, bucket_name: str = "pet-images") -> str | None:
    """Normalize a stored object path or a legacy public Storage URL.

    New assessment rows persist only the object path.  This helper keeps the
    private-bucket migration backwards compatible with older rows that stored
    Supabase's full ``/object/public/<bucket>/...`` URL.
    """

    if not image_uri:
        return None
    marker = f"/{bucket_name}/"
    parsed_path = unquote(urlparse(image_uri).path)
    if marker in parsed_path:
        return parsed_path.split(marker, 1)[1]
    if "://" in image_uri:
        return None
    return image_uri.lstrip("/")


def create_assessment_signed_url(
    access_token: str,
    image_uri: str | None,
    expires_in: int = 900,
) -> str | None:
    """Create a short-lived URL after Storage RLS authorizes the caller."""

    object_path = storage_object_path(image_uri)
    if not object_path:
        return image_uri
    bucket = create_user_storage_client(access_token).from_("pet-images")
    result = bucket.create_signed_url(object_path, expires_in)
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return result.get("signedURL") or result.get("signedUrl")
    return getattr(result, "signed_url", None) or getattr(result, "signedURL", None)
