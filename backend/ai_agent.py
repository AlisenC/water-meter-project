import re
import anthropic
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from .database import engine

router = APIRouter()

class Question(BaseModel):
    question: str

schema_description = """
Table: readings

Columns:
- id INTEGER PRIMARY KEY
- mi TEXT — the household or meter identifier (e.g. "Unit 3A")
- reading FLOAT — the cumulative meter reading value in cubic metres
- record_date DATE — the date the reading was recorded (YYYY-MM-DD)
- unit INTEGER — 0 = main meter, 1 = sub-meter
"""

def extract_sql(raw: str) -> str:
    match = re.search(r"```(?:sql)?\s*([\s\S]+?)```", raw, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _ask_anthropic(question: str, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)

    sql_response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=(
            "You are a SQL expert working with a SQLite water meter database. "
            "Write only SELECT queries — never INSERT, UPDATE, DELETE, or DROP. "
            "Return ONLY the raw SQL query with no markdown, no code fences, and no explanation."
        ),
        messages=[{"role": "user", "content": f"Schema:\n{schema_description}\n\nQuestion: {question}"}],
    )

    sql = extract_sql(next(b.text for b in sql_response.content if b.type == "text"))

    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        return {"error": "Only SELECT queries are permitted.", "sql_attempted": sql}

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            data_rows = [dict(r) for r in result]
    except Exception as e:
        return {"error": str(e), "sql_attempted": sql}

    explanation = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=(
            "You are a helpful assistant analysing water meter data. "
            "Answer in 2–4 plain-English sentences. "
            "Quote specific numbers and dates from the data. "
            "Use 'm³' for cubic metres. "
            "Do not repeat the SQL or describe how you got the answer."
        ),
        messages=[{"role": "user", "content": f"Question: {question}\n\nQuery result ({len(data_rows)} row(s)):\n{data_rows}"}],
    )

    return {
        "sql": sql,
        "result": data_rows,
        "answer": next(b.text for b in explanation.content if b.type == "text"),
    }


def _ask_openai(question: str, api_key: str) -> dict:
    try:
        import openai
    except ImportError:
        raise HTTPException(status_code=400, detail="openai package is not installed on this server.")

    client = openai.OpenAI(api_key=api_key)

    sql_response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a SQL expert working with a SQLite water meter database. "
                    "Write only SELECT queries — never INSERT, UPDATE, DELETE, or DROP. "
                    "Return ONLY the raw SQL query with no markdown, no code fences, and no explanation."
                ),
            },
            {"role": "user", "content": f"Schema:\n{schema_description}\n\nQuestion: {question}"},
        ],
    )

    sql = extract_sql(sql_response.choices[0].message.content)

    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        return {"error": "Only SELECT queries are permitted.", "sql_attempted": sql}

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            data_rows = [dict(r) for r in result]
    except Exception as e:
        return {"error": str(e), "sql_attempted": sql}

    explanation = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant analysing water meter data. "
                    "Answer in 2–4 plain-English sentences. "
                    "Quote specific numbers and dates from the data. "
                    "Use 'm³' for cubic metres. "
                    "Do not repeat the SQL or describe how you got the answer."
                ),
            },
            {"role": "user", "content": f"Question: {question}\n\nQuery result ({len(data_rows)} row(s)):\n{data_rows}"},
        ],
    )

    return {
        "sql": sql,
        "result": data_rows,
        "answer": explanation.choices[0].message.content,
    }


@router.post("/ask")
def ask_ai(
    q: Question,
    x_api_key: str | None = Header(default=None),
    x_api_provider: str | None = Header(default=None),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="No API key configured. Add your Anthropic or OpenAI key in the API Settings panel.")

    provider = (x_api_provider or "anthropic").lower()
    try:
        if provider == "openai":
            return _ask_openai(q.question, x_api_key)
        else:
            return _ask_anthropic(q.question, x_api_key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI request failed: {str(e)}")
