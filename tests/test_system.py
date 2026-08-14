"""Deployment-safety tests for environment checks and readiness probes."""

import pytest

import app.main as main_module
from app.config import EnvironmentValidationError, validate_environment
from app.readiness import ReadinessResult, expected_database_revisions


def _deployed_environment(**overrides):
    values = {
        "APP_ENV": "staging",
        "DATABASE_URL": "postgresql://runtime.example/petto",
        "MIGRATION_DATABASE_URL": "postgresql://migration.example:5432/petto",
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "test-publishable-key",
        "GEMINI_API_KEY": "test-gemini-key",
        "ENABLE_MOCK_DATA": "false",
    }
    values.update(overrides)
    return values


def test_health_is_liveness_only(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ready_returns_200_when_database_and_revision_are_current(client, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "check_readiness",
        lambda: ReadinessResult(
            ready=True,
            database="available",
            migration="current",
            current_revisions=("0005_storage_owner_rls",),
            expected_revisions=("0005_storage_owner_rls",),
        ),
    )

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_ready_returns_503_for_migration_mismatch(client, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "check_readiness",
        lambda: ReadinessResult(
            ready=False,
            database="available",
            migration="out_of_date",
            current_revisions=("0001_baseline_schema",),
            expected_revisions=("0005_storage_owner_rls",),
            reason="migration_mismatch",
        ),
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["reason"] == "migration_mismatch"


def test_staging_requires_a_session_or_direct_migration_url():
    values = _deployed_environment()
    values.pop("MIGRATION_DATABASE_URL")

    with pytest.raises(EnvironmentValidationError, match="MIGRATION_DATABASE_URL"):
        validate_environment(values, require_migration_url=True)


def test_migrations_reject_transaction_pooler_port():
    values = _deployed_environment(
        MIGRATION_DATABASE_URL="postgresql://migration.example:6543/petto"
    )

    with pytest.raises(EnvironmentValidationError, match="port 6543"):
        validate_environment(values, require_migration_url=True)


def test_production_rejects_wildcard_cors():
    values = _deployed_environment(APP_ENV="production", ALLOWED_ORIGINS="*")

    with pytest.raises(EnvironmentValidationError, match="ALLOWED_ORIGINS"):
        validate_environment(values)


def test_repository_expected_revision_is_current_head():
    assert expected_database_revisions() == ("0013_wardrobe_reward_ids",)
