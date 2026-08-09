# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock
from app import models

# ITC-03: AI Health Assessment Pipeline
# Test ID: ai_health_assessment_pipeline

@pytest.fixture
def mock_external_apis(monkeypatch):
    """Mocks Supabase and Gemini APIs."""
    mock_storage_client = MagicMock()
    mock_bucket = MagicMock()
    mock_storage_client.from_.return_value = mock_bucket
    mock_bucket.get_public_url.return_value = "https://mock-supabase.com/image.jpg"
    monkeypatch.setattr(
        "app.routers.assessments.create_user_storage_client",
        lambda access_token: mock_storage_client,
    )

    mock_gemini = MagicMock()
    mock_gemini_resp = MagicMock()
    mock_gemini_resp.text = "1. OBSERVATIONS\n2. POTENTIAL CONCERNS\n3. RECOMMENDED ACTIONS\n4. DISCLAIMER\nRisk: LOW"
    mock_gemini.models.generate_content.return_value = mock_gemini_resp
    monkeypatch.setattr("app.routers.assessments.gemini_client", mock_gemini)
    
    return mock_bucket, mock_gemini


def test_assessment_e2e_success(auth_client, pet, mock_external_apis, db):
    """ITC-03-TC-01: End-to-End Success Path"""
    mock_storage, mock_gemini = mock_external_apis
    
    # Create fake image
    fake_image = b"\xff\xd8\xff\xe0fake image bytes"
    
    response = auth_client.post(
        "/api/v1/assessments",
        data={"pet_id": pet.id, "symptom_description": "Lethargic"},
        files={"image": ("test.jpg", fake_image, "image/jpeg")}
    )
    
    assert response.status_code == 200
    
    # Verify DB
    db_assessment = db.query(models.HealthAssessment).filter(models.HealthAssessment.pet_id == pet.id).first()
    assert db_assessment is not None
    assert db_assessment.risk_level == models.RiskLevel.LOW
    assert db_assessment.status == "completed"
    assert db_assessment.error_code is None


def test_assessment_gemini_fallback(
    auth_client, pet, mock_external_apis, db, monkeypatch
):
    """ITC-03-TC-02: Gemini API Down Fallback Mechanism"""
    mock_storage, mock_gemini = mock_external_apis
    
    # Simulate Gemini 503 error
    mock_gemini.models.generate_content.side_effect = Exception("503 Service Unavailable")
    monkeypatch.setattr("app.routers.assessments.AI_RETRY_BASE_SECONDS", 0)
    
    fake_image = b"\xff\xd8\xff\xe0fake image bytes"
    
    response = auth_client.post(
        "/api/v1/assessments",
        data={"pet_id": pet.id, "symptom_description": "Limping"},
        files={"image": ("test.jpg", fake_image, "image/jpeg")}
    )
    
    assert response.status_code == 200
    
    # Verify DB records an explicit failure without inventing a medical risk.
    db_assessment = db.query(models.HealthAssessment).filter(models.HealthAssessment.pet_id == pet.id).first()
    assert db_assessment is not None
    assert db_assessment.status == "failed"
    assert db_assessment.risk_level is None
    assert db_assessment.ai_raw_response is None
    assert db_assessment.error_code == "AI_UPSTREAM_ERROR"


def test_assessment_supabase_failure(auth_client, pet, mock_external_apis, db):
    """ITC-03-TC-03: Supabase Storage Upload Failure"""
    mock_storage, mock_gemini = mock_external_apis
    
    # Simulate Supabase 500 error
    mock_storage.upload.side_effect = Exception("500 Internal Server Error")
    
    fake_image = b"\xff\xd8\xff\xe0fake image bytes"
    
    response = auth_client.post(
        "/api/v1/assessments",
        data={"pet_id": pet.id, "symptom_description": "Vomiting"},
        files={"image": ("test.jpg", fake_image, "image/jpeg")}
    )
    
    # Expecting failure immediately
    assert response.status_code == 502
    
    # Verify Gemini was never called
    mock_gemini.models.generate_content.assert_not_called()
    
    # Verify no row inserted
    db_assessment = db.query(models.HealthAssessment).filter(models.HealthAssessment.pet_id == pet.id).first()
    assert db_assessment is None
