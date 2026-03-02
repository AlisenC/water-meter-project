from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from .database import engine
from openai import OpenAI

router = APIRouter()

client = OpenAI()

class Question(BaseModel):
    question: str

schema_description = """
Database: water_meter.db

Table: readings

Columns:
id INTEGER PRIMARY KEY
mi TEXT (household name)
reading FLOAT (meter value)
record_date DATE
unit INTEGER (0 or 1)
"""

@router.post("/ask")
def ask_ai(q: Question):

    prompt = f"""
You are a data analyst.

Database schema:
{schema_description}

User question:
{q.question}

Write a SQL query that answers the question.
Return ONLY the SQL query.
"""

    sql_response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    sql_query = sql_response.choices[0].message.content.strip()

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = [dict(r) for r in result]

    except Exception as e:
        return {
            "error": str(e),
            "sql_attempted": sql_query
        }

    explanation_prompt = f"""
User question:
{q.question}

SQL used:
{sql_query}

Result:
{rows}

Explain the answer in plain English.
"""

    explanation = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": explanation_prompt}]
    )

    return {
        "sql": sql_query,
        "result": rows,
        "answer": explanation.choices[0].message.content
    }
