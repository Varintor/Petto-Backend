# -*- coding: utf-8 -*-
"""UTC-05: Health Assessment module (AI fallback + file validation)."""


class _FakeBucket:
    def upload(self, path, file, file_options):
        return None

    def get_public_url(self, path):
        return f"https://images.test/{path}"


class _FakeStorage:
    def from_(self, name):
        return _FakeBucket()


class _FakeSupabase:
    storage = _FakeStorage()


def test_assessment_ai_unavailable_is_recorded_as_failed(auth_client, pet, monkeypatch):
    # Gemini disabled -> explicit retryable failure; Supabase storage mocked.
    monkeypatch.setattr("app.routers.assessments.supabase", _FakeSupabase())
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
