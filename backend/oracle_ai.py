import re
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .database import engine as sqlite_engine
from .oracle_connection import is_connected, get_connection

router = APIRouter()

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
# Status & Init                                                                #
# --------------------------------------------------------------------------- #

@router.get("/oracle/status")
def oracle_status():
    connected, error = is_connected()
    if not connected:
        return {"connected": False, "version": None, "error": error}
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION FROM V$INSTANCE")
                row = cur.fetchone()
                version = row[0] if row else None
        return {"connected": True, "version": version, "error": None}
    except Exception as exc:
        return {"connected": True, "version": None, "error": str(exc)}


@router.post("/oracle/init")
def oracle_init():
    connected, error = is_connected()
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    # Use PL/SQL EXECUTE IMMEDIATE to silently skip ORA-955 (table exists)
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
            EXECUTE IMMEDIATE '
                CREATE TABLE wm_billing_statements (
                    id                   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    billing_month        NUMBER(2) NOT NULL,
                    billing_year         NUMBER(4) NOT NULL,
                    period_end_month     NUMBER(2),
                    period_end_year      NUMBER(4),
                    total_consumption_kl NUMBER(10,4) NOT NULL,
                    billing_cost_aud     NUMBER(10,2) NOT NULL,
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
        with get_connection() as conn:
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
def oracle_sync():
    connected, error = is_connected()
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    with sqlite_engine.connect() as conn:
        readings = [
            dict(r)
            for r in conn.execute(
                text("SELECT id, mi, reading, record_date, unit FROM readings")
            )
        ]
        bills = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT id, billing_month, billing_year, period_end_month, period_end_year,"
                    " total_consumption_kl, billing_cost_aud, source_filename"
                    " FROM billing_statements"
                )
            )
        ]

    synced_readings = 0
    synced_bills = 0

    try:
        with get_connection() as conn:
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
                            "sqlite_id": r["id"],
                            "mi": r["mi"],
                            "reading": r["reading"],
                            "record_date": r["record_date"],
                            "unit": r["unit"],
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
                                       total_consumption_kl = :total_consumption_kl,
                                       billing_cost_aud = :billing_cost_aud,
                                       synced_at = CURRENT_TIMESTAMP
                        WHEN NOT MATCHED THEN
                            INSERT (billing_month, billing_year, period_end_month, period_end_year,
                                    total_consumption_kl, billing_cost_aud, source_filename,
                                    sqlite_id, synced_at)
                            VALUES (:billing_month, :billing_year, :period_end_month, :period_end_year,
                                    :total_consumption_kl, :billing_cost_aud, :source_filename,
                                    :sqlite_id, CURRENT_TIMESTAMP)
                        """,
                        {
                            "sqlite_id": b["id"],
                            "billing_month": b["billing_month"],
                            "billing_year": b["billing_year"],
                            "period_end_month": b.get("period_end_month"),
                            "period_end_year": b.get("period_end_year"),
                            "total_consumption_kl": b["total_consumption_kl"],
                            "billing_cost_aud": b["billing_cost_aud"],
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
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required for embedding generation.")

    connected, error = is_connected()
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    provider = (x_api_provider or "anthropic").lower()

    with sqlite_engine.connect() as conn:
        readings = [
            dict(r)
            for r in conn.execute(
                text("SELECT id, mi, reading, record_date FROM readings ORDER BY id")
            )
        ]

    if not readings:
        return {"embedded": 0, "provider": provider, "dims": 0}

    descriptions = [
        f"{r['mi']} meter reading {r['reading']} kL on {r['record_date']}"
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
        with get_connection() as conn:
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
                            "reading_id": r["id"],
                            "household": r["mi"],
                            "reading_value": r["reading"],
                            "record_date": r["record_date"],
                            "description": desc,
                            "embedding": emb_vec,
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
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required for vector search.")

    connected, error = is_connected()
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
        with get_connection() as conn:
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


def _run_oracle_sql(sql: str) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _ask_oracle_anthropic(question: str, api_key: str) -> dict:
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
        data_rows = _run_oracle_sql(sql)
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
        messages=[
            {"role": "user", "content": f"Question: {question}\n\nQuery result ({len(data_rows)} row(s)):\n{data_rows}"}
        ],
    )
    return {
        "sql": sql,
        "result": data_rows,
        "answer": next(b.text for b in exp_msg.content if b.type == "text"),
    }


def _ask_oracle_openai(question: str, api_key: str) -> dict:
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
        data_rows = _run_oracle_sql(sql)
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
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required for Oracle AI queries.")

    connected, error = is_connected()
    if not connected:
        raise HTTPException(status_code=503, detail=f"Oracle not connected: {error}")

    provider = (x_api_provider or "anthropic").lower()
    try:
        if provider == "openai":
            return _ask_oracle_openai(q.question, x_api_key)
        return _ask_oracle_anthropic(q.question, x_api_key)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Oracle AI request failed: {str(exc)}")
