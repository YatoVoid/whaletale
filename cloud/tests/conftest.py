from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from whaletale_cloud.models import Base
from whaletale_cloud.seed import SeedResult, seed_demo


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """A Postgres for the test session.

    Uses WHALETALE_TEST_DATABASE_URL if set (CI service container, or a local
    `docker compose -f docker/compose.cloud.yml up`), otherwise starts a
    throwaway container via testcontainers.
    """
    external = os.getenv("WHALETALE_TEST_DATABASE_URL")
    if external:
        yield external
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg.get_connection_url()


def _fresh_database(pg_url: str, name: str) -> str:
    admin = create_engine(pg_url, future=True, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    return pg_url.rsplit("/", 1)[0] + "/" + name


@pytest.fixture(scope="session")
def engine(pg_url: str) -> Iterator[Engine]:
    """Schema-only engine on a dedicated database, seeded once by `seed_result`.

    Per-test isolation is a savepoint rollback (see `seeded` / `db`), so the
    seed survives the whole session.
    """
    url = _fresh_database(pg_url, "whaletale_test")
    eng = create_engine(url, future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def seed_result(engine: Engine) -> SeedResult:
    with Session(engine) as s:
        res = seed_demo(s, weeks=6)
        s.commit()
    return res


@pytest.fixture
def seeded(engine: Engine, seed_result: SeedResult) -> Iterator[tuple[Session, SeedResult]]:
    """The shared seed plus a session whose writes roll back after the test."""
    connection = engine.connect()
    txn = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session, seed_result
    finally:
        session.close()
        txn.rollback()
        connection.close()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A bare session (over the seeded database) that rolls back after the test."""
    connection = engine.connect()
    txn = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        txn.rollback()
        connection.close()


@pytest.fixture(scope="session")
def isolated_engine(pg_url: str) -> Iterator[Engine]:
    """A separate empty database for tests that TRUNCATE or assert absolute row
    counts and must not see the shared seed."""
    url = _fresh_database(pg_url, "whaletale_test_isolated")
    eng = create_engine(url, future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def clean_db(isolated_engine: Engine) -> Iterator[Session]:
    _truncate(isolated_engine)
    session = Session(isolated_engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    finally:
        session.close()


def _truncate(engine: Engine) -> None:
    with engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def api_client(isolated_engine: Engine) -> Iterator[object]:
    """A FastAPI TestClient whose session and rate limiter are bound to the
    isolated database. Truncates first; commits are real (ingest idempotency
    needs them)."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from whaletale_cloud.api.app import create_app
    from whaletale_cloud.api.deps import get_session
    from whaletale_cloud.api.security import RateLimiter

    _truncate(isolated_engine)
    maker = sessionmaker(isolated_engine, expire_on_commit=False)

    def _session_override() -> Iterator[Session]:
        s = maker()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app = create_app()
    app.state.rate_limiter = RateLimiter()
    app.dependency_overrides[get_session] = _session_override
    with TestClient(app) as client:
        client.db = maker
        yield client
