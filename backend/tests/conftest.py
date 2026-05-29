"""Pytest fixtures for the test suite.

Strategy
--------
- Unit tests (test_jwt, test_security, test_phone, test_otp_dev) need NO DB.
- Integration tests use a real PostgreSQL test database `roadside_test`
  (PostGIS extension required) created on first run.

To enable integration tests:
    1. Have Docker Compose stack running (postgres healthy).
    2. Create the test database:
       docker exec -it roadside-postgres psql -U roadside -d postgres \\
         -c "CREATE DATABASE roadside_test;"
       docker exec -it roadside-postgres psql -U roadside -d roadside_test \\
         -c "CREATE EXTENSION IF NOT EXISTS postgis; \\
             CREATE EXTENSION IF NOT EXISTS pgcrypto;"
    3. Run: pytest backend/tests/

Why the engine is function-scoped
---------------------------------
pytest-asyncio 0.25.x supports `asyncio_default_fixture_loop_scope` but NOT
`asyncio_default_test_loop_scope`, so tests still get one event loop per
function. A session-scoped async engine binds asyncpg's internal Futures to
the loop that created it; reusing that engine from a different test loop
raises "Future attached to a different loop" or "another operation is in
progress." The fix: create a fresh engine per test (cheap — just sets up a
pool ref; doesn't reconnect). Schema bootstrap runs once via the
`_schema_initialized` guard so we don't pay drop_all/create_all per test.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import AsyncGenerator as AsyncGen

import pytest_asyncio

# Force test-mode env BEFORE importing app modules so config picks it up
os.environ["APP_ENV"] = "development"
os.environ["DEBUG"] = "false"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-must-be-at-least-32-bytes-long-ok"
# Force Twilio dev-fallback mode — clear any placeholder values from .env
os.environ["TWILIO_VERIFY_SERVICE_SID"] = ""
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["TWILIO_AUTH_TOKEN"] = ""


# Override DATABASE_URL to point at the test DB before importing anything else
_test_db_url = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://roadside:roadside@localhost:5432/roadside_test",
)
os.environ["DATABASE_URL"] = _test_db_url
os.environ["DATABASE_SYNC_URL"] = _test_db_url.replace("+asyncpg", "")


from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.database import Base  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Incident, Message, Provider, SecurityEvent, TaskLog, User  # noqa: E402, F401

# The slowapi Limiter is a process-wide singleton with module-level state.
# Across a full test run we issue more requests than RATE_LIMIT_AUTH allows
# (10/min) and the singleton starts returning 429s mid-suite — flakily, on
# whichever tests cross the threshold. Disable rate limiting in tests; it has
# its own dedicated coverage where needed.
from app.api.auth import limiter as _auth_limiter  # noqa: E402
from app.api.incidents import limiter as _incidents_limiter  # noqa: E402
_auth_limiter.enabled = False
_incidents_limiter.enabled = False


# One-time bootstrap guard: schema setup (drop_all/create_all + extensions)
# runs only on the first test that needs a DB. Subsequent tests TRUNCATE
# instead of recreating.
_schema_initialized = False


@pytest_asyncio.fixture
async def _engine():
    """Per-test async engine. First call also bootstraps the schema."""
    global _schema_initialized
    engine = create_async_engine(_test_db_url, future=True)
    if not _schema_initialized:
        async with engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        _schema_initialized = True
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine) -> AsyncGen[AsyncSession, None]:
    """Per-test session. Tables are truncated after each test."""
    sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    # Clean up
    from sqlalchemy import text
    async with _engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE security_events, task_logs, messages, "
                "incidents, providers, users RESTART IDENTITY CASCADE;"
            )
        )


@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client that talks to the in-process FastAPI app.

    Overrides the get_db dependency to share the per-test session.
    """
    from app.database import get_db

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
