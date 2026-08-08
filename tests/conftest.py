# -*- coding: utf-8 -*-
"""Shared pytest fixtures for the Petto backend test suite.

Uses an in-memory SQLite database (StaticPool) with the app's SQLAlchemy
models, overriding the `get_db` dependency. External services (Supabase
Auth/Storage, Gemini) are disabled via empty env vars and mocked per-test.
"""
import os

# Must be set BEFORE importing app.* so module-level clients init as None and
# database.py builds a throwaway engine (the real engine is overridden below).
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["APP_ENV"] = "test"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

import pytest
from sqlalchemy import create_engine, BigInteger
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient


# SQLite has no BIGINT autoincrement; map BigInteger -> INTEGER so identity
# primary keys behave like the Postgres ones during tests.
@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):  # noqa: ANN001
    return "INTEGER"


from app import models                                # noqa: E402
from app.database import get_db, get_session_factory  # noqa: E402
from app.auth import get_current_user, get_supabase_uid  # noqa: E402
from app.main import app                               # noqa: E402

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db():
    models.Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db):
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    # Slow endpoints (assessments) open their own short-lived sessions via
    # this factory — point it at the shared in-memory test engine.
    app.dependency_overrides[get_session_factory] = lambda: TestingSessionLocal
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def user(db):
    u = models.User(email="owner@test.com", name="Owner", supabase_uid="uid-owner")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def pet(db, user):
    p = models.Pet(user_id=user.id, name="Buddy", species="Dog", weight_kg=10)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def auth_client(client, user):
    """A client whose get_current_user resolves to the seeded `user`."""
    app.dependency_overrides[get_current_user] = lambda: user
    # Assessments authenticate via the raw uid (no DB in the dependency);
    # resolve it to the seeded user's supabase uid.
    app.dependency_overrides[get_supabase_uid] = lambda: user.supabase_uid
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_supabase_uid, None)
