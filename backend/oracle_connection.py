import os
import contextlib

try:
    import oracledb
    _ORACLE_AVAILABLE = True
except ImportError:
    _ORACLE_AVAILABLE = False

_pool = None

ORACLE_WALLET_DIR     = os.getenv("ORACLE_WALLET_DIR")
ORACLE_SERVICE_NAME   = os.getenv("ORACLE_SERVICE_NAME")
ORACLE_USER           = os.getenv("ORACLE_USER")
ORACLE_PASSWORD       = os.getenv("ORACLE_PASSWORD")
ORACLE_WALLET_PASSWORD= os.getenv("ORACLE_WALLET_PASSWORD")


def _env_configured() -> bool:
    return bool(ORACLE_WALLET_DIR and ORACLE_SERVICE_NAME and ORACLE_USER and ORACLE_PASSWORD)


def _get_pool():
    global _pool
    if _pool is None:
        if not _ORACLE_AVAILABLE:
            raise RuntimeError("oracledb package not installed on server")
        if not _env_configured():
            raise RuntimeError(
                "Oracle not configured — add a connection profile in Settings "
                "or set ORACLE_WALLET_DIR, ORACLE_SERVICE_NAME, ORACLE_USER, ORACLE_PASSWORD env vars"
            )
        kwargs = dict(
            user=ORACLE_USER,
            password=ORACLE_PASSWORD,
            dsn=ORACLE_SERVICE_NAME,
            config_dir=ORACLE_WALLET_DIR,
            wallet_location=ORACLE_WALLET_DIR,
            min=1,
            max=5,
            increment=1,
        )
        if ORACLE_WALLET_PASSWORD:
            kwargs["wallet_password"] = ORACLE_WALLET_PASSWORD
        _pool = oracledb.create_pool(**kwargs)
    return _pool


@contextlib.contextmanager
def get_connection_with_wallet(
    wallet_dir: str,
    service_name: str,
    user: str,
    password: str,
    wallet_password: str | None = None,
):
    """Direct (non-pooled) wallet-based connection using caller-supplied credentials."""
    if not _ORACLE_AVAILABLE:
        raise RuntimeError("oracledb package not installed on server")
    kwargs = dict(
        user=user,
        password=password,
        dsn=service_name,
        config_dir=wallet_dir,
        wallet_location=wallet_dir,
    )
    if wallet_password:
        kwargs["wallet_password"] = wallet_password
    conn = oracledb.connect(**kwargs)
    try:
        yield conn
    finally:
        conn.close()


def is_connected(
    wallet_dir: str | None = None,
    service_name: str | None = None,
    user: str | None = None,
    password: str | None = None,
    wallet_password: str | None = None,
) -> tuple[bool, str | None]:
    """Returns (connected, error).

    If wallet_dir/service_name/user/password are all provided, tests with those.
    Otherwise falls back to the server-side env-var pool.
    """
    if not _ORACLE_AVAILABLE:
        return False, "oracledb package not installed on server"

    if wallet_dir and service_name and user and password:
        try:
            with get_connection_with_wallet(wallet_dir, service_name, user, password, wallet_password) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 'ok' FROM DUAL")
                    cur.fetchone()
            return True, None
        except Exception as exc:
            return False, str(exc)

    if not _env_configured():
        return False, "Oracle not configured — add a connection profile in Settings or set server env vars"
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
    wallet_dir: str | None = None,
    service_name: str | None = None,
    user: str | None = None,
    password: str | None = None,
    wallet_password: str | None = None,
):
    """Context manager yielding an Oracle connection.

    Uses wallet args when all four required ones are provided; otherwise uses the env-var pool.
    """
    if wallet_dir and service_name and user and password:
        with get_connection_with_wallet(wallet_dir, service_name, user, password, wallet_password) as conn:
            yield conn
    else:
        pool = _get_pool()
        with pool.acquire() as conn:
            yield conn
