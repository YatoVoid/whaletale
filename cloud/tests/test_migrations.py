from __future__ import annotations

import os
import subprocess
from pathlib import Path

_CLOUD = Path(__file__).resolve().parents[1]


def _alembic(*args: str, url: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if url is not None:
        env["DATABASE_URL"] = url
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=_CLOUD,
        env=env,
        capture_output=True,
        text=True,
    )


def test_upgrade_head_on_empty_db_then_check_is_clean(pg_url: str, tmp_path: Path) -> None:
    """spec 14a: migrations apply cleanly to an empty DB, and head matches the
    models (catches a forgotten autogenerate)."""
    import sqlalchemy as sa

    dbname = "mig_check_db"
    admin = sa.create_engine(pg_url, future=True, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(sa.text(f'DROP DATABASE IF EXISTS "{dbname}"'))
        c.execute(sa.text(f'CREATE DATABASE "{dbname}"'))
    admin.dispose()

    target = pg_url.rsplit("/", 1)[0] + "/" + dbname
    try:
        up = _alembic("upgrade", "head", url=target)
        assert up.returncode == 0, up.stderr

        check = _alembic("check", url=target)
        assert check.returncode == 0, (
            "alembic check found model/migration drift:\n" + check.stdout + check.stderr
        )

        down = _alembic("downgrade", "base", url=target)
        assert down.returncode == 0, down.stderr
    finally:
        admin = sa.create_engine(pg_url, future=True, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(sa.text(f'DROP DATABASE IF EXISTS "{dbname}"'))
        admin.dispose()


def test_single_head_revision() -> None:
    out = _alembic("heads")
    assert out.returncode == 0, out.stderr
    heads = [ln for ln in out.stdout.splitlines() if ln.strip()]
    assert len(heads) == 1, f"expected one migration head, got: {heads}"
