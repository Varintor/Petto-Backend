"""User-scoped Supabase Storage client and object path tests."""

import re

import pytest

from app import storage


def test_storage_client_uses_publishable_key_and_user_jwt(monkeypatch):
    captured = {}
    expected_client = object()

    def fake_create_client(url, headers, *, is_async, timeout):
        captured.update(
            url=url,
            headers=headers,
            is_async=is_async,
            timeout=timeout,
        )
        return expected_client

    monkeypatch.setattr(storage, "SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setattr(storage, "SUPABASE_KEY", "publishable-key")
    monkeypatch.setattr(storage, "STORAGE_TIMEOUT_SECONDS", 17)
    monkeypatch.setattr(storage, "create_storage_client", fake_create_client)

    client = storage.create_user_storage_client("verified-user-jwt")

    assert client is expected_client
    assert captured == {
        "url": "https://project.supabase.co/storage/v1",
        "headers": {
            "apikey": "publishable-key",
            "Authorization": "Bearer verified-user-jwt",
        },
        "is_async": False,
        "timeout": 17,
    }


@pytest.mark.parametrize("missing", ["url", "key", "token"])
def test_storage_client_rejects_missing_configuration(monkeypatch, missing):
    monkeypatch.setattr(
        storage,
        "SUPABASE_URL",
        "" if missing == "url" else "https://project.supabase.co",
    )
    monkeypatch.setattr(
        storage,
        "SUPABASE_KEY",
        "" if missing == "key" else "publishable-key",
    )
    token = "" if missing == "token" else "verified-user-jwt"

    with pytest.raises(storage.StorageConfigurationError):
        storage.create_user_storage_client(token)


def test_assessment_object_path_is_owner_scoped_and_unique():
    first = storage.assessment_object_path("user-uid", 42, ".png")
    second = storage.assessment_object_path("user-uid", 42, ".png")

    assert re.fullmatch(r"user-uid/42/[0-9a-f]{32}\.png", first)
    assert first != second
