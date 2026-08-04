import io
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from .database import SessionLocal, engine as sqlite_engine
from .models import OracleProfile
from .oracle_connection import is_connected, get_connection

router = APIRouter()

# Wallet storage — persists in Docker volume via DATA_DIR=/app/data
DATA_DIR   = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
WALLET_DIR = os.path.join(DATA_DIR, "wallets")
os.makedirs(os.path.join(WALLET_DIR, "tmp"), exist_ok=True)

ORACLE_SCHEMA = """
Table: WM_READINGS

Columns:
- ID NUMBER PRIMARY KEY
- MI VARCHAR2(200) — household or meter identifier (e.g. "Unit 3A")
- READING NUMBER — cumulative meter reading in cubic metres
- RECORD_DATE TIMESTAMP — date the reading was recorded
- UNIT NUMBER — 0 = main meter, 1 = sub-meter
- SYNCED_AT TIMESTAMP — when this row was last synced from SQLite
"""


class Question(BaseModel):
    question: str


class VectorQuery(BaseModel):
    query: str
    top_k: int = 5


# --------------------------------------------------------------------------- #
# Profile helpers                                                               #
# --------------------------------------------------------------------------- #

def _resolve_oracle_creds(profile_id: int | None) -> tuple:
    """Return (wallet_dir, service_name, user, password, wallet_password) from profile or (None,)*5."""
    if not profile_id:
        return None, None, None, None, None
    db = SessionLocal()
    try:
        p = db.query(OracleProfile).filter(OracleProfile.id == profile_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Oracle profile not found.")
        return p.wallet_path, p.service_name, p.username, p.password, p.wallet_password
    finally:
        db.close()


def _parse_tnsnames(content: str) -> list[str]:
    """Extract top-level alias names from tnsnames.ora."""
    return re.findall(r"^([\w][\w._-]*)\s*=", content, re.MULTILINE)


# --------------------------------------------------------------------------- #
# Profile endpoints                                                             #
# --------------------------------------------------------------------------- #

@router.post("/oracle/wallet/parse")
async def oracle_wallet_parse(file: UploadFile = File(...)):
    """Upload a wallet ZIP, extract it, return service names and a temp_id for profile creation."""
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Wallet must be a .zip file.")

    data = await file.read()
    temp_id = str(uuid.uuid4())
    temp_dir = os.path.join(WALLET_DIR, "tmp", temp_id)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            zf.extractall(temp_dir)
    except zipfile.BadZipFile:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid ZIP file.")

    tnsnames_path = os.path.join(temp_dir, "tnsnames.ora")
    if not os.path.exists(tnsnames_path):
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Wallet ZIP does not contain tnsnames.ora.")

    with open(tnsnames_path) as f:
        content = f.read()

    services = _parse_tnsnames(content)
    if not services:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="No service names found in tnsnames.ora.")

    return {"services": services, "temp_id": temp_id}


@router.get("/oracle/profiles")
def oracle_profiles_list():
    """List all saved Oracle connection profiles (passwords excluded)."""
    db = SessionLocal()
    try:
        profiles = db.query(OracleProfile).order_by(OracleProfile.created_at.desc()).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "service_name": p.service_name,
                "username": p.username,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in profiles
        ]
    finally:
        db.close()


@router.post("/oracle/profiles")
async def oracle_profile_create(
    name: str = Form(...),
    service_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    wallet_password: str | None = Form(default=None),
    temp_id: str = Form(...),
):
    """Create a new Oracle connection profile from a previously parsed wallet."""
    temp_dir = os.path.join(WALLET_DIR, "tmp", temp_id)
    if not os.path.isdir(temp_dir):
        raise HTTPException(status_code=400, detail="Wallet temp ID not found — re-upload the wallet.")

    db = SessionLocal()
    try:
        profile = OracleProfile(
            name=name,
            wallet_path="",  # filled in after we know the ID
            service_name=service_name,
            username=username,
            password=password,
            wallet_password=wallet_password or None,
            created_at=datetime.utcnow(),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        permanent_dir = os.path.join(WALLET_DIR, str(profile.id))
        shutil.move(temp_dir, permanent_dir)

        profile.wallet_path = permanent_dir
        db.commit()

        return {
            "id": profile.id,
            "name": profile.name,
            "service_name": profile.service_name,
            "username": profile.username,
            "created_at": profile.created_at.isoformat(),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@router.delete("/oracle/profiles/{profile_id}")
def oracle_profile_delete(profile_id: int):
    """Delete a profile and its wallet files from disk."""
    db = SessionLocal()
    try:
        p = db.query(OracleProfile).filter(OracleProfile.id == profile_id).first()
        if not p:
            raise HTTPException(status_code=404, detail="Profile not found.")
        wallet_dir = p.wallet_path
        db.delete(p)
        db.commit()
    finally:
        db.close()

    if wallet_dir and os.path.isdir(wallet_dir):
        shutil.rmtree(wallet_dir, ignore_errors=True)

    return {"ok": True}


# --------------------------------------------------------------------------- #
# Status & Init                                                                #
# --------------------------------------------------------------------------- #

@router.get("/oracle/status")
def oracle_status(x_oracle_profile_id: int | None = Header(default=None)):
    wallet_dir, service_name, user, password, wallet_password = _resolve_oracle_creds(x_oracle_profile_id)
    connected, error = is_connected(wallet_dir, service_name, user, password, wallet_password)
    if not connected:
        return {"connected": False, "version": None, "error": error}
    try:
        with get_connection(wallet_dir, service_name, user, password, wallet_password) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION FROM V$INSTANCE")
                row = cur.fetchone()
                version = row[0] if row else None
        return {"connected": True, "version": version, "error": None}
    except Exception as exc:
        return {"connected": True, "version": None, "error": str(exc)}


@router.post("/oracle/init")
def oracle_init(x_oracle_profile_id: int | None = Header(default=None)):
    wallet_dir, service_name, user, password, wallet_password = _resolve_oracle_creds(x_oracle_profile_id)
    connected, error = is_connected(wallet_dir, service_name, user, password, wallet_password)
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    ddl_blocks = [
        """
        BEGIN
            EXECUTE IMMEDIATE '
                CREATE TABLE wm_readings (
                    id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    mi         VARCHAR2(200) NOT NULL,
                    reading    NUMBER(10,4) NOT NULL,
                    record_date TIMESTAMP NOT NULL,
                    unit       NUMBER(1) DEFAULT 1,
                    sqlite_id  NUMBER,
                    synced_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ';
        EXCEPTION WHEN OTHERS THEN
            IF SQLCODE = -955 THEN NULL; END IF;
        END;
        """,
        """
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE wm_billing_statements';
        EXCEPTION WHEN OTHERS THEN
            IF SQLCODE != -942 THEN RAISE; END IF;
        END;
        """,
        """
        BEGIN
            EXECUTE IMMEDIATE '
                CREATE TABLE wm_billing_statements (
                    id                   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    billing_month        NUMBER(2) NOT NULL,
                    billing_year         NUMBER(4) NOT NULL,
                    period_end_month     NUMBER(2),
                    period_end_year      NUMBER(4),
                    total_units_consumed NUMBER(10,4) NOT NULL,
                    total_cost           NUMBER(10,2) NOT NULL,
                    cost_per_unit        NUMBER(10,4),
                    source_filename      VARCHAR2(500),
                    sqlite_id            NUMBER,
                    synced_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ';
        EXCEPTION WHEN OTHERS THEN
            IF SQLCODE = -955 THEN NULL; END IF;
        END;
        """,
        """
        BEGIN
            EXECUTE IMMEDIATE '
                CREATE TABLE wm_readings_vectors (
                    id            NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    reading_id    NUMBER NOT NULL,
                    household     VARCHAR2(200),
                    reading_value NUMBER(10,4),
                    record_date   TIMESTAMP,
                    description   CLOB,
                    embedding     VECTOR(*, FLOAT32)
                )
            ';
        EXCEPTION WHEN OTHERS THEN
            IF SQLCODE = -955 THEN NULL; END IF;
        END;
        """,
    ]

    try:
        with get_connection(wallet_dir, service_name, user, password, wallet_password) as conn:
            with conn.cursor() as cur:
                for block in ddl_blocks:
                    cur.execute(block)
            conn.commit()
        return {"ok": True, "message": "Tables created (or already exist)"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DDL failed: {str(exc)}")


# --------------------------------------------------------------------------- #
# Data Sync                                                                    #
# --------------------------------------------------------------------------- #

@router.post("/oracle/sync")
def oracle_sync(x_oracle_profile_id: int | None = Header(default=None)):
    wallet_dir, service_name, user, password, wallet_password = _resolve_oracle_creds(x_oracle_profile_id)
    connected, error = is_connected(wallet_dir, service_name, user, password, wallet_password)
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    with sqlite_engine.connect() as conn:
        readings = [
            dict(r)
            for r in conn.execute(text("SELECT id, mi, reading, record_date, unit FROM readings"))
        ]
        bills = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT id, billing_month, billing_year, period_end_month, period_end_year,"
                    " total_units_consumed, total_cost, cost_per_unit, source_filename FROM billing_statements"
                )
            )
        ]

    synced_readings = 0
    synced_bills = 0

    try:
        with get_connection(wallet_dir, service_name, user, password, wallet_password) as conn:
            with conn.cursor() as cur:
                for r in readings:
                    cur.execute(
                        """
                        MERGE INTO wm_readings dest
                        USING (SELECT :sqlite_id AS sqlite_id FROM DUAL) src
                        ON (dest.sqlite_id = src.sqlite_id)
                        WHEN MATCHED THEN
                            UPDATE SET mi = :mi, reading = :reading,
                                       record_date = :record_date, unit = :unit,
                                       synced_at = CURRENT_TIMESTAMP
                        WHEN NOT MATCHED THEN
                            INSERT (mi, reading, record_date, unit, sqlite_id, synced_at)
                            VALUES (:mi, :reading, :record_date, :unit, :sqlite_id, CURRENT_TIMESTAMP)
                        """,
                        {
                            "sqlite_id": r["id"], "mi": r["mi"],
                            "reading": r["reading"], "record_date": r["record_date"], "unit": r["unit"],
                        },
                    )
                    synced_readings += 1

                for b in bills:
                    cur.execute(
                        """
                        MERGE INTO wm_billing_statements dest
                        USING (SELECT :sqlite_id AS sqlite_id FROM DUAL) src
                        ON (dest.sqlite_id = src.sqlite_id)
                        WHEN MATCHED THEN
                            UPDATE SET billing_month = :billing_month, billing_year = :billing_year,
                                       total_units_consumed = :total_units_consumed,
                                       total_cost = :total_cost,
                                       cost_per_unit = :cost_per_unit,
                                       synced_at = CURRENT_TIMESTAMP
                        WHEN NOT MATCHED THEN
                            INSERT (billing_month, billing_year, period_end_month, period_end_year,
                                    total_units_consumed, total_cost, cost_per_unit, source_filename,
                                    sqlite_id, synced_at)
                            VALUES (:billing_month, :billing_year, :period_end_month, :period_end_year,
                                    :total_units_consumed, :total_cost, :cost_per_unit, :source_filename,
                                    :sqlite_id, CURRENT_TIMESTAMP)
                        """,
                        {
                            "sqlite_id": b["id"],
                            "billing_month": b["billing_month"], "billing_year": b["billing_year"],
                            "period_end_month": b.get("period_end_month"),
                            "period_end_year": b.get("period_end_year"),
                            "total_units_consumed": b["total_units_consumed"],
                            "total_cost": b["total_cost"],
                            "cost_per_unit": b.get("cost_per_unit"),
                            "source_filename": b.get("source_filename"),
                        },
                    )
                    synced_bills += 1

            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(exc)}")

    return {"synced_readings": synced_readings, "synced_bills": synced_bills}


# --------------------------------------------------------------------------- #
# Embeddings                                                                   #
# --------------------------------------------------------------------------- #

# Mirrors backend/main.py's _to_units — duplicated here rather than imported to avoid a circular
# import (main.py imports this module's router).
_GALLONS_PER_UNIT = 0.748


def _to_units(reading: float, unit: int) -> float:
    return reading if unit == 1 else reading / _GALLONS_PER_UNIT


def _embed_openai(texts: list[str], api_key: str) -> list[list[float]]:
    import openai
    client = openai.OpenAI(api_key=api_key)
    response = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in response.data]


def _embed_voyage(texts: list[str], api_key: str) -> list[list[float]]:
    import voyageai
    client = voyageai.Client(api_key=api_key)
    result = client.embed(texts, model="voyage-3")
    return result.embeddings


@router.post("/oracle/embed-sync")
def oracle_embed_sync(
    x_api_key: str | None = Header(default=None),
    x_api_provider: str | None = Header(default=None),
    x_oracle_profile_id: int | None = Header(default=None),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required for embedding generation.")

    wallet_dir, service_name, user, password, wallet_password = _resolve_oracle_creds(x_oracle_profile_id)
    connected, error = is_connected(wallet_dir, service_name, user, password, wallet_password)
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    provider = (x_api_provider or "anthropic").lower()

    with sqlite_engine.connect() as conn:
        readings = [
            dict(r)
            for r in conn.execute(text("SELECT id, mi, reading, record_date, unit FROM readings ORDER BY id"))
        ]

    if not readings:
        return {"embedded": 0, "provider": provider, "dims": 0}

    for r in readings:
        r["units_of_water"] = round(_to_units(r["reading"], r["unit"]), 3)

    descriptions = [
        f"{r['mi']} meter reading {r['units_of_water']} units of water on {r['record_date']}"
        for r in readings
    ]

    try:
        if provider == "openai":
            embeddings = _embed_openai(descriptions, x_api_key)
            dims = 1536
        else:
            embeddings = _embed_voyage(descriptions, x_api_key)
            dims = 1024
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Embedding generation failed: {str(exc)}")

    try:
        import oracledb
        with get_connection(wallet_dir, service_name, user, password, wallet_password) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM wm_readings_vectors")
                for r, desc, emb in zip(readings, descriptions, embeddings):
                    emb_vec = oracledb.vector(emb, oracledb.VECTOR_SUBTYPE_FLOAT32)
                    cur.execute(
                        """
                        INSERT INTO wm_readings_vectors
                            (reading_id, household, reading_value, record_date, description, embedding)
                        VALUES (:reading_id, :household, :reading_value, :record_date, :description, :embedding)
                        """,
                        {
                            "reading_id": r["id"], "household": r["mi"],
                            "reading_value": r["units_of_water"], "record_date": r["record_date"],
                            "description": desc, "embedding": emb_vec,
                        },
                    )
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Oracle insert failed: {str(exc)}")

    return {"embedded": len(readings), "provider": provider, "dims": dims}


@router.post("/oracle/vector-search")
def oracle_vector_search(
    q: VectorQuery,
    x_api_key: str | None = Header(default=None),
    x_api_provider: str | None = Header(default=None),
    x_oracle_profile_id: int | None = Header(default=None),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required for vector search.")

    wallet_dir, service_name, user, password, wallet_password = _resolve_oracle_creds(x_oracle_profile_id)
    connected, error = is_connected(wallet_dir, service_name, user, password, wallet_password)
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    provider = (x_api_provider or "anthropic").lower()

    try:
        if provider == "openai":
            query_emb = _embed_openai([q.query], x_api_key)[0]
        else:
            query_emb = _embed_voyage([q.query], x_api_key)[0]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Query embedding failed: {str(exc)}")

    try:
        import oracledb
        query_vec = oracledb.vector(query_emb, oracledb.VECTOR_SUBTYPE_FLOAT32)
        with get_connection(wallet_dir, service_name, user, password, wallet_password) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT household, reading_value, record_date, description,
                           VECTOR_DISTANCE(embedding, :qvec, COSINE) AS distance
                    FROM wm_readings_vectors
                    ORDER BY VECTOR_DISTANCE(embedding, :qvec, COSINE)
                    FETCH FIRST :top_k ROWS ONLY
                    """,
                    {"qvec": query_vec, "top_k": q.top_k},
                )
                cols = [d[0].lower() for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]

        for row in rows:
            if row.get("record_date"):
                row["record_date"] = str(row["record_date"])
            dist = float(row.pop("distance", 1.0))
            row["similarity"] = round((1 - dist) * 100, 1)

        return {"results": rows, "query": q.query}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {str(exc)}")


# --------------------------------------------------------------------------- #
# Oracle NL2SQL (Ask Oracle)                                                   #
# --------------------------------------------------------------------------- #

def _extract_sql(raw: str) -> str:
    match = re.search(r"```(?:sql)?\s*([\s\S]+?)```", raw, re.IGNORECASE)
    return match.group(1).strip() if match else raw.strip()


def _run_oracle_sql(
    sql: str,
    wallet_dir: str | None = None,
    service_name: str | None = None,
    user: str | None = None,
    password: str | None = None,
    wallet_password: str | None = None,
) -> list[dict]:
    with get_connection(wallet_dir, service_name, user, password, wallet_password) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _ask_oracle_anthropic(question, api_key, wallet_dir=None, service_name=None, user=None, password=None, wallet_password=None):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    sql_msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=(
            "You are a SQL expert working with Oracle Database 26ai. "
            "Write only SELECT queries — never INSERT, UPDATE, DELETE, or DROP. "
            "Use Oracle SQL syntax: SYSDATE (not NOW()), TO_DATE for date literals, "
            "FETCH FIRST n ROWS ONLY (not LIMIT). "
            "Return ONLY the raw SQL with no markdown, no code fences, no explanation."
        ),
        messages=[{"role": "user", "content": f"Schema:\n{ORACLE_SCHEMA}\n\nQuestion: {question}"}],
    )
    sql = _extract_sql(next(b.text for b in sql_msg.content if b.type == "text"))

    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        return {"error": "Only SELECT queries are permitted.", "sql": sql, "result": [], "answer": ""}

    try:
        data_rows = _run_oracle_sql(sql, wallet_dir, service_name, user, password, wallet_password)
    except Exception as exc:
        return {"error": str(exc), "sql": sql, "result": [], "answer": ""}

    exp_msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=(
            "You are a helpful assistant analysing water meter data from Oracle 26ai. "
            "Answer in 2–4 plain-English sentences. Quote specific numbers and dates from the data. "
            "Use 'kL' for kilolitres. Do not repeat the SQL."
        ),
        messages=[{"role": "user", "content": f"Question: {question}\n\nQuery result ({len(data_rows)} row(s)):\n{data_rows}"}],
    )
    return {
        "sql": sql,
        "result": data_rows,
        "answer": next(b.text for b in exp_msg.content if b.type == "text"),
    }


def _ask_oracle_openai(question, api_key, wallet_dir=None, service_name=None, user=None, password=None, wallet_password=None):
    import openai
    client = openai.OpenAI(api_key=api_key)

    sql_resp = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a SQL expert working with Oracle Database 26ai. "
                    "Write only SELECT queries. Use Oracle SQL syntax: SYSDATE, TO_DATE, FETCH FIRST n ROWS ONLY. "
                    "Return ONLY the raw SQL with no markdown, code fences, or explanation."
                ),
            },
            {"role": "user", "content": f"Schema:\n{ORACLE_SCHEMA}\n\nQuestion: {question}"},
        ],
    )
    sql = _extract_sql(sql_resp.choices[0].message.content)

    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        return {"error": "Only SELECT queries are permitted.", "sql": sql, "result": [], "answer": ""}

    try:
        data_rows = _run_oracle_sql(sql, wallet_dir, service_name, user, password, wallet_password)
    except Exception as exc:
        return {"error": str(exc), "sql": sql, "result": [], "answer": ""}

    exp_resp = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant analysing water meter data from Oracle 26ai. "
                    "Answer in 2–4 sentences. Quote specific numbers. Use 'kL'. Do not repeat the SQL."
                ),
            },
            {"role": "user", "content": f"Question: {question}\n\nResult ({len(data_rows)} row(s)):\n{data_rows}"},
        ],
    )
    return {
        "sql": sql,
        "result": data_rows,
        "answer": exp_resp.choices[0].message.content,
    }


@router.post("/oracle/ask")
def oracle_ask(
    q: Question,
    x_api_key: str | None = Header(default=None),
    x_api_provider: str | None = Header(default=None),
    x_oracle_profile_id: int | None = Header(default=None),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required for Oracle AI queries.")

    wallet_dir, service_name, user, password, wallet_password = _resolve_oracle_creds(x_oracle_profile_id)
    connected, error = is_connected(wallet_dir, service_name, user, password, wallet_password)
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    provider = (x_api_provider or "anthropic").lower()
    try:
        if provider == "openai":
            return _ask_oracle_openai(q.question, x_api_key, wallet_dir, service_name, user, password, wallet_password)
        return _ask_oracle_anthropic(q.question, x_api_key, wallet_dir, service_name, user, password, wallet_password)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Oracle AI request failed: {str(exc)}")
