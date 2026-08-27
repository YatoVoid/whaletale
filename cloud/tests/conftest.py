from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from whaletale_cloud.models import Base


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


@pytest.fixture(scope="session")
def engine(pg_url: str) -> Iterator[Engine]:
    eng = create_engine(pg_url, future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """A session wrapped in a transaction rolled back after each test, so tests
    stay isolated without recreating the schema. `create_savepoint` keeps a
    failed flush (e.g. an expected IntegrityError) from poisoning the outer
    transaction."""
    connection = engine.connect()
    txn = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        txn.rollback()
        connection.close()


@pytest.fixture
def clean_db(engine: Engine) -> Iterator[Session]:
    """Like `db` but truncates every table first for tests that need to assert
    on absolute row counts or run the seed."""
    with engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
    try:
        yield session
        session.commit()
    finally:
        session.close()
