import re
import anthropic
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from .database import engine

router = APIRouter()

client = anthropic.Anthropic()

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
    # Strip markdown code fences if the model wrapped the query
    match = re.search(r"```(?:sql)?\s*([\s\S]+?)```", raw, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw.strip()

@router.post("/ask")
def ask_ai(q: Question):

    sql_response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=(
            "You are a SQL expert working with a SQLite water meter database. "
            "Write only SELECT queries — never INSERT, UPDATE, DELETE, or DROP. "
            "Return ONLY the raw SQL query with no markdown, no code fences, and no explanation."
        ),
        messages=[
            {
                "role": "user",
                "content": f"Schema:\n{schema_description}\n\nQuestion: {q.question}",
            },
        ],
    )

    sql_query = extract_sql(next(b.text for b in sql_response.content if b.type == "text"))

    if not re.match(r"^\s*SELECT\b", sql_query, re.IGNORECASE):
        return {"error": "Only SELECT queries are permitted.", "sql_attempted": sql_query}

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = [dict(r) for r in result]
    except Exception as e:
        return {"error": str(e), "sql_attempted": sql_query}

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
        messages=[
            {
                "role": "user",
                "content": (
                    f"Question: {q.question}\n\n"
                    f"Query result ({len(rows)} row(s)):\n{rows}"
                ),
            },
        ],
    )

    return {
        "sql": sql_query,
        "result": rows,
        "answer": next(b.text for b in explanation.content if b.type == "text"),
    }
