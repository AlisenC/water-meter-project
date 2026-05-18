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


@contextlib.contextmanager
def get_connection_with_creds(dsn: str, user: str, password: str):
    """Direct (non-pooled) connection using caller-supplied credentials."""
    if not _ORACLE_AVAILABLE:
        raise RuntimeError("oracledb package not installed on server")
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    try:
        yield conn
    finally:
        conn.close()


def is_connected(
    dsn: str | None = None,
    user: str | None = None,
    password: str | None = None,
) -> tuple[bool, str | None]:
    """Returns (connected, error).

    If dsn/user/password are all provided, tests with those credentials directly.
    Otherwise falls back to the server-side env-var pool.
    """
    if not _ORACLE_AVAILABLE:
        return False, "oracledb package not installed on server"

    if dsn and user and password:
        try:
            with get_connection_with_creds(dsn, user, password) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 'ok' FROM DUAL")
                    cur.fetchone()
            return True, None
        except Exception as exc:
            return False, str(exc)

    if not _env_configured():
        return False, "Oracle not configured — enter credentials in Settings or set server env vars"
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
def get_connection(
    dsn: str | None = None,
    user: str | None = None,
    password: str | None = None,
):
    """Context manager yielding an Oracle connection.

    Uses caller-supplied credentials when all three are provided;
    otherwise uses the env-var pool.
    """
    if dsn and user and password:
        with get_connection_with_creds(dsn, user, password) as conn:
            yield conn
    else:
        pool = _get_pool()
        with pool.acquire() as conn:
            yield conn
