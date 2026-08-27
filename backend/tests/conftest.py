import os

import pytest
from sqlalchemy import text

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL environment variable must be set to a dedicated test "
        "Postgres database — never point it at real data. e.g. "
        "postgresql+psycopg://user:password@host:5432/water_meter_test"
    )
# backend.database reads DATABASE_URL at import time; route handlers create
# their own SessionLocal() per request rather than taking an injected
# dependency, so pointing every DB-backed test at the right database means
# setting this before backend.database (and anything importing it) loads.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from backend.database import engine  # noqa: E402

_TABLES = [
    "leak_main_meter_readings",
    "leak_submeter_readings",
    "leak_sessions",
    "billing_statements",
    "readings",
    "oracle_profiles",
]


@pytest.fixture(autouse=True)
def clean_db():
    """Truncate every app table before each test for a known-empty starting state.

    The app's routes open their own SessionLocal() per request rather than
    accepting an injected session, so a transactional-rollback fixture isn't
    workable here — truncating is the simplest reliable isolation.
    """
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from backend.main import app

    return TestClient(app)
