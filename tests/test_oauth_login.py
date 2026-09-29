from app.auth import SupabaseAuthContext, get_supabase_auth_context
from app.main import app
from app import models


def test_google_oauth_creates_backend_owner(client, db):
    app.dependency_overrides[get_supabase_auth_context] = lambda: SupabaseAuthContext(
        supabase_uid="google-user-1",
        access_token="google-access-token",
        email="google.owner@example.com",
        user_metadata={
            "full_name": "Google Owner",
            "picture": "https://example.com/avatar.png",
        },
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer google-access-token"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "google.owner@example.com"
    assert response.json()["name"] == "Google Owner"
    owner = db.query(models.User).filter_by(supabase_uid="google-user-1").one()
    assert owner.avatar_uri == "https://example.com/avatar.png"


def test_oauth_reuses_matching_unlinked_owner(client, db):
    owner = models.User(email="existing@example.com", name="Existing")
    db.add(owner)
    db.commit()
    app.dependency_overrides[get_supabase_auth_context] = lambda: SupabaseAuthContext(
        supabase_uid="linked-google-user",
        access_token="google-access-token",
        email="existing@example.com",
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer google-access-token"},
    )

    assert response.status_code == 200
    db.refresh(owner)
    assert owner.supabase_uid == "linked-google-user"
