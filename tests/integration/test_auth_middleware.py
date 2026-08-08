# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from app import models

# ITC-01: Token Authentication and Route Protection
# Test ID: auth_token_and_route_protection

def test_auth_middleware_valid_token(client, db, monkeypatch):
    """ITC-01-TC-01: Valid JWT Token grants access"""
    # Setup test data
    db.add(models.User(email="authuser@test.com", name="Auth User", supabase_uid="valid-uid"))
    db.commit()
    
    # Mock supabase client
    mock_supabase = MagicMock()
    mock_user_resp = MagicMock()
    mock_user_resp.user.id = "valid-uid"
    mock_supabase.auth.get_user.return_value = mock_user_resp
    
    monkeypatch.setattr("app.auth.supabase", mock_supabase)
    
    # Request without token overriding
    response = client.get(
        "/api/v1/pets", 
        headers={"Authorization": "Bearer valid_token_123"}
    )
    
    # Expected: 200 OK
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_auth_middleware_invalid_token(client, monkeypatch):
    """ITC-01-TC-02: Expired/Invalid Token is blocked"""
    # Mock supabase to throw exception when verifying token
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("Expired token")
    
    monkeypatch.setattr("app.auth.supabase", mock_supabase)
    
    response = client.get(
        "/api/v1/pets", 
        headers={"Authorization": "Bearer expired_token"}
    )
    
    # Expected: 401 Unauthorized
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_auth_middleware_missing_token(client):
    """ITC-01-TC-03: Missing Token blocks access early"""
    # No Authorization header
    response = client.get("/api/v1/pets")
    
    # FastAPI HTTPBearer returns 403 by default, but in our setup it returns 401
    assert response.status_code == 401
