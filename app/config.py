"""Runtime environment validation for local and deployed environments."""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlparse

from dotenv import load_dotenv


load_dotenv()

DEPLOYED_ENVIRONMENTS = {"staging", "production"}
VALID_ENVIRONMENTS = {"development", "test", *DEPLOYED_ENVIRONMENTS}
TRUE_VALUES = {"1", "true", "yes", "on"}


class EnvironmentValidationError(RuntimeError):
    """Raised when required runtime configuration is missing or unsafe."""


def _is_enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUE_VALUES


def _has_valid_url(value: str | None, *, schemes: set[str]) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in schemes and bool(parsed.hostname)


def _has_valid_database_url(value: str | None) -> bool:
    if not value:
        return False
    if value.startswith("sqlite:"):
        return True
    return _has_valid_url(value, schemes={"postgres", "postgresql"})


def validate_environment(
    environ: Mapping[str, str] | None = None,
    *,
    require_migration_url: bool = False,
) -> str:
    """Validate environment variables and return the normalized APP_ENV.

    Secret values are never included in validation errors. Development keeps
    external AI/Supabase integrations optional so unit tests and local API work
    remain possible, while staging and production fail fast when incomplete.
    """

    source = os.environ if environ is None else environ
    app_env = source.get("APP_ENV", "development").strip().lower()
    errors: list[str] = []

    if app_env not in VALID_ENVIRONMENTS:
        errors.append(
            "APP_ENV must be one of development, test, staging, or production"
        )

    database_url = source.get("DATABASE_URL", "").strip()
    if not database_url:
        errors.append("DATABASE_URL is required")
    elif not _has_valid_database_url(database_url):
        errors.append("DATABASE_URL must be a valid PostgreSQL or SQLite URL")

    if app_env in DEPLOYED_ENVIRONMENTS:
        required = ("SUPABASE_URL", "SUPABASE_KEY", "GEMINI_API_KEY")
        errors.extend(f"{name} is required for {app_env}" for name in required if not source.get(name, "").strip())

        if database_url.startswith("sqlite"):
            errors.append(f"DATABASE_URL cannot use SQLite in {app_env}")

        supabase_url = source.get("SUPABASE_URL", "").strip()
        if supabase_url and not _has_valid_url(supabase_url, schemes={"https"}):
            errors.append("SUPABASE_URL must be a valid HTTPS URL")

        if _is_enabled(source.get("ENABLE_MOCK_DATA")):
            errors.append(f"ENABLE_MOCK_DATA must be disabled in {app_env}")

    if app_env == "production":
        origins = [
            origin.strip()
            for origin in source.get("ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        ]
        if not origins or "*" in origins:
            errors.append("ALLOWED_ORIGINS must be explicit in production")

    if require_migration_url:
        migration_url = source.get("MIGRATION_DATABASE_URL", "").strip()
        if app_env in DEPLOYED_ENVIRONMENTS and not migration_url:
            errors.append(f"MIGRATION_DATABASE_URL is required for {app_env} migrations")
        elif migration_url:
            if not _has_valid_url(migration_url, schemes={"postgres", "postgresql"}):
                errors.append("MIGRATION_DATABASE_URL must be a valid PostgreSQL URL")
            elif urlparse(migration_url).port == 6543:
                errors.append(
                    "MIGRATION_DATABASE_URL must use a direct or session-pooler connection, not transaction-pooler port 6543"
                )

    if errors:
        raise EnvironmentValidationError("; ".join(errors))

    return app_env
