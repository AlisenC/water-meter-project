import contextlib

try:
    import oracledb
    _ORACLE_AVAILABLE = True
except ImportError:
    _ORACLE_AVAILABLE = False


@contextlib.contextmanager
def get_connection_with_wallet(
    wallet_dir: str,
    service_name: str,
    user: str,
    password: str,
    wallet_password: str | None = None,
):
    if not _ORACLE_AVAILABLE:
        raise RuntimeError("oracledb import failed — rebuild the Docker image to install dependencies")
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
    wallet_dir: str | None,
    service_name: str | None,
    user: str | None,
    password: str | None,
    wallet_password: str | None = None,
) -> tuple[bool, str | None]:
    if not _ORACLE_AVAILABLE:
        return False, "oracledb import failed — rebuild the Docker image to install dependencies"
    if not (wallet_dir and service_name and user and password):
        return False, "No Oracle connection profile selected — add one in Settings"
    try:
        with get_connection_with_wallet(wallet_dir, service_name, user, password, wallet_password) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 'ok' FROM DUAL")
                cur.fetchone()
        return True, None
    except Exception as exc:
        return False, str(exc)


@contextlib.contextmanager
def get_connection(
    wallet_dir: str | None,
    service_name: str | None,
    user: str | None,
    password: str | None,
    wallet_password: str | None = None,
):
    with get_connection_with_wallet(wallet_dir, service_name, user, password, wallet_password) as conn:
        yield conn
