import psycopg
import pytest

from app.config import get_settings

pytestmark = pytest.mark.db


def test_db_test_accepts_a_connection():
    url = (
        get_settings()
        .TEST_DATABASE_URL.get_secret_value()
        .replace("postgresql+psycopg://", "postgresql://")
    )
    with psycopg.connect(url, connect_timeout=3) as conn:
        assert conn.execute("select 1").fetchone() == (1,)
