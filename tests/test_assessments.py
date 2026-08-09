# -*- coding: utf-8 -*-
"""UTC-05: Health Assessment module (AI fallback + file validation)."""


class _FakeBucket:
    def __init__(self):
        self.uploaded_path = None

    def upload(self, path, file, file_options):
        self.uploaded_path = path
        return None

    def get_public_url(self, path):
        return f"https://images.test/{path}"


class _FakeStorageClient:
    def __init__(self):
        self.bucket = _FakeBucket()

    def from_(self, name):
        assert name == "pet-images"
        return self.bucket


def test_assessment_ai_unavailable_is_recorded_as_failed(auth_client, pet, monkeypatch):
    # Gemini disabled -> explicit retryable failure; Supabase storage mocked.
    storage_client = _FakeStorageClient()

    def user_storage_client(access_token):
        assert access_token == "test-access-token"
        return storage_client

    monkeypatch.setattr(
        "app.routers.assessments.create_user_storage_client",
        user_storage_client,
    )
    monkeypatch.setattr("app.routers.assessments.gemini_client", None)

    r = auth_client.post(
        "/api/v1/assessments",
        data={"pet_id": str(pet.id), "symptom_description": "Lethargic, loss of appetite"},
        files={"image": ("symptom.jpg", b"\xff\xd8\xff\xe0fake-jpeg", "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "failed"
    assert data["risk_level"] is None
    assert data["ai_raw_response"] is None
    assert data["error_code"] == "AI_SERVICE_UNAVAILABLE"
    assert data["pet_id"] == pet.id
    assert storage_client.bucket.uploaded_path.startswith(
        f"uid-owner/{pet.id}/"
    )
    assert storage_client.bucket.uploaded_path.endswith(".jpg")


def test_assessment_rejects_non_image(auth_client, pet):
    r = auth_client.post(
        "/api/v1/assessments",
        data={"pet_id": str(pet.id), "symptom_description": "test"},
        files={"image": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "File must be an image"


def test_assessment_rejects_spoofed_image_content_type(auth_client, pet):
    r = auth_client.post(
        "/api/v1/assessments",
        data={"pet_id": str(pet.id), "symptom_description": "test"},
        files={"image": ("fake.jpg", b"not-an-image", "image/jpeg")},
    )
    assert r.status_code == 400
    assert "invalid image" in r.json()["detail"].lower()


def test_assessment_rejects_image_over_size_limit(auth_client, pet, monkeypatch):
    monkeypatch.setattr("app.routers.assessments.MAX_IMAGE_BYTES", 8)
    r = auth_client.post(
        "/api/v1/assessments",
        data={"pet_id": str(pet.id), "symptom_description": "test"},
        files={"image": ("large.jpg", b"\xff\xd8\xff" + b"x" * 10, "image/jpeg")},
    )
    assert r.status_code == 413
