import os
import contextlib

try:
    import oracledb
    _ORACLE_AVAILABLE = True
except ImportError:
    _ORACLE_AVAILABLE = False

_pool = None

ORACLE_DSN = os.getenv("ORACLE_DSN")
ORACLE_USER = os.getenv("ORACLE_USER")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD")


def _env_configured() -> bool:
    return bool(ORACLE_DSN and ORACLE_USER and ORACLE_PASSWORD)


def _get_pool():
    global _pool
    if _pool is None:
        if not _ORACLE_AVAILABLE:
            raise RuntimeError("oracledb package not installed on server")
        if not _env_configured():
            raise RuntimeError(
                "Oracle env vars not set — configure ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD"
            )
        _pool = oracledb.create_pool(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_DSN,
            min=1,
            max=5,
            increment=1,
        )
    return _pool


def is_connected() -> tuple[bool, str | None]:
    """Returns (connected: bool, error: str | None)."""
    if not _ORACLE_AVAILABLE:
        return False, "oracledb package not installed on server"
    if not _env_configured():
        return False, "Oracle env vars not set (ORACLE_DSN, ORACLE_USER, ORACLE_PASSWORD)"
    try:
        pool = _get_pool()
        with pool.acquire() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 'ok' FROM DUAL")
                cur.fetchone()
        return True, None
    except Exception as exc:
        return False, str(exc)


@contextlib.contextmanager
def get_connection():
    """Context manager yielding a pooled Oracle connection."""
    pool = _get_pool()
    with pool.acquire() as conn:
        yield conn
