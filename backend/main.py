from fastapi import FastAPI, UploadFile, File, HTTPException, Header
import csv
import os
import base64
import json
import re
from io import StringIO
from fastapi.middleware.cors import CORSMiddleware
from .database import SessionLocal, engine
from .models import Base, Reading, BillingStatement
from datetime import datetime, date as date_type
from pydantic import BaseModel
from collections import defaultdict
from statistics import median
from .ai_agent import router as ai_router
import anthropic as anthropic_sdk

GAP_MULTIPLIER = 1.5

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)
app = FastAPI()

class ReadingCreate(BaseModel):
    household: str
    amount: float

# AI Agent Router
app.include_router(ai_router, prefix="/ai")

# CORS
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173")
origins = [o.strip() for o in _raw_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}

# Add a reading
@app.post("/readings")
async def add_reading(reading: ReadingCreate):
    db = SessionLocal()

    new_reading = Reading(
        mi=reading.household,
        reading=reading.amount,
        record_date=datetime.utcnow(),
        unit=1
    )

    db.add(new_reading)
    db.commit()
    db.refresh(new_reading)
    db.close()

    return new_reading

# Get all readings
@app.get("/readings")
async def get_readings():
    db = SessionLocal()
    readings = db.query(Reading).all()
    db.close()
    return readings

def validate_reading(row: dict, row_num: int) -> dict | None:
    raw = row.get("reading", "").strip()
    if not raw:
        return {"row_num": row_num, "reason": "missing_reading", "raw_value": raw}
    try:
        float(raw)
    except ValueError:
        return {"row_num": row_num, "reason": "invalid_reading", "raw_value": raw}
    return None

# Import CSV
@app.post("/import-csv")
async def import_csv(file: UploadFile = File(...)):
    db = SessionLocal()

    contents = await file.read()
    csv_text = contents.decode("utf-8-sig")

    reader = csv.DictReader(StringIO(csv_text), delimiter=",")

    inserted = 0
    skipped = 0
    errors = []

    for row_num, row in enumerate(reader, start=1):
        reading_error = validate_reading(row, row_num)
        if reading_error:
            errors.append(reading_error)
            skipped += 1
            continue

        try:
            parsed_date = datetime.strptime(row["record_date"], "%Y-%m-%d")

            reading = Reading(
                mi=row["mi"],
                reading=float(row["reading"]),
                record_date=parsed_date,
                unit=int(row["unit"])
            )

            db.add(reading)
            inserted += 1

        except Exception as e:
            print("Skipping row:", row, e)
            skipped += 1

    db.commit()
    db.close()

    return {"inserted": inserted, "skipped": skipped, "errors": errors}

# Delete a reading
@app.delete("/readings/{reading_id}")
async def delete_reading(reading_id: int):
    db = SessionLocal()
    reading = db.query(Reading).filter(Reading.id == reading_id).first()
    if not reading:
        db.close()
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Reading not found")
    db.delete(reading)
    db.commit()
    db.close()
    return {"ok": True}

EXTRACTION_PROMPT = """Return ONLY a valid JSON object with these exact keys (no markdown, no explanation):
{
  "billing_period_start_month": <integer 1-12>,
  "billing_period_start_year": <integer>,
  "billing_period_end_month": <integer 1-12>,
  "billing_period_end_year": <integer>,
  "total_consumption_kl": <float, kilolitres>,
  "total_cost_aud": <float, AUD total payable>
}
Rules:
- total_consumption_kl: total water used in kL (1 cubic metre = 1 kL).
- total_cost_aud: total amount payable in AUD.
- Use null for any field that cannot be determined.
- Return only the JSON object. No other text."""


def _parse_ai_json(raw_text: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw_text, re.IGNORECASE)
    cleaned = match.group(1).strip() if match else raw_text.strip()
    return json.loads(cleaned)


def _extract_with_anthropic(pdf_b64: str, filename: str, api_key: str) -> str:
    client = anthropic_sdk.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=512,
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
            {"type": "text", "text": EXTRACTION_PROMPT},
        ]}],
    )
    return next(b.text for b in response.content if b.type == "text")


def _extract_with_openai(pdf_b64: str, filename: str, api_key: str) -> str:
    try:
        import openai
    except ImportError:
        raise HTTPException(status_code=400, detail="openai package is not installed on this server.")
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=512,
        messages=[{"role": "user", "content": [
            {"type": "file", "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{pdf_b64}"}},
            {"type": "text", "text": EXTRACTION_PROMPT},
        ]}],
    )
    return response.choices[0].message.content


# Import a billing statement PDF
@app.post("/import-billing")
async def import_billing(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
    x_api_provider: str | None = Header(default=None),
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="No API key configured. Add your Anthropic or OpenAI key in the API Settings panel.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    provider = (x_api_provider or "anthropic").lower()
    try:
        if provider == "openai":
            raw_text = _extract_with_openai(pdf_b64, file.filename, x_api_key)
        else:
            raw_text = _extract_with_anthropic(pdf_b64, file.filename, x_api_key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {str(e)}")

    try:
        extracted = _parse_ai_json(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail=f"AI returned non-JSON response: {raw_text[:300]}")

    required = [
        "billing_period_start_month", "billing_period_start_year",
        "billing_period_end_month", "billing_period_end_year",
        "total_consumption_kl", "total_cost_aud",
    ]
    missing = [f for f in required if extracted.get(f) is None]
    if missing:
        raise HTTPException(status_code=422, detail=f"Could not extract: {missing}. Raw: {raw_text[:300]}")

    start_month = int(extracted["billing_period_start_month"])
    start_year = int(extracted["billing_period_start_year"])

    db = SessionLocal()
    existing = db.query(BillingStatement).filter(
        BillingStatement.billing_month == start_month,
        BillingStatement.billing_year == start_year,
    ).first()
    if existing:
        db.close()
        raise HTTPException(status_code=409, detail=f"A statement for {start_month}/{start_year} already exists (id={existing.id}).")

    stmt = BillingStatement(
        billing_month=start_month,
        billing_year=start_year,
        period_end_month=int(extracted["billing_period_end_month"]),
        period_end_year=int(extracted["billing_period_end_year"]),
        total_consumption_kl=float(extracted["total_consumption_kl"]),
        billing_cost_aud=float(extracted["total_cost_aud"]),
        source_filename=file.filename,
        imported_at=datetime.utcnow(),
    )
    db.add(stmt)
    db.commit()
    db.refresh(stmt)
    db.close()

    return {
        "id": stmt.id,
        "billing_month": stmt.billing_month,
        "billing_year": stmt.billing_year,
        "period_end_month": stmt.period_end_month,
        "period_end_year": stmt.period_end_year,
        "total_consumption_kl": stmt.total_consumption_kl,
        "billing_cost_aud": stmt.billing_cost_aud,
        "source_filename": stmt.source_filename,
    }


# List all billing statements
@app.get("/billing-statements")
async def get_billing_statements():
    db = SessionLocal()
    stmts = db.query(BillingStatement).order_by(
        BillingStatement.billing_year.desc(),
        BillingStatement.billing_month.desc(),
    ).all()
    db.close()
    return [
        {
            "id": s.id,
            "billing_month": s.billing_month,
            "billing_year": s.billing_year,
            "period_end_month": s.period_end_month,
            "period_end_year": s.period_end_year,
            "total_consumption_kl": s.total_consumption_kl,
            "billing_cost_aud": s.billing_cost_aud,
            "source_filename": s.source_filename,
            "imported_at": s.imported_at.isoformat() if s.imported_at else None,
        }
        for s in stmts
    ]


# Delete a billing statement
@app.delete("/billing-statements/{stmt_id}")
async def delete_billing_statement(stmt_id: int):
    db = SessionLocal()
    stmt = db.query(BillingStatement).filter(BillingStatement.id == stmt_id).first()
    if not stmt:
        db.close()
        raise HTTPException(status_code=404, detail="Billing statement not found")
    db.delete(stmt)
    db.commit()
    db.close()
    return {"ok": True}


# Verify billing statements against main meter readings
@app.get("/billing-verify")
async def billing_verify():
    db = SessionLocal()
    stmts = db.query(BillingStatement).order_by(
        BillingStatement.billing_year,
        BillingStatement.billing_month,
    ).all()
    main_readings = (
        db.query(Reading)
        .filter(Reading.mi == "MAIN", Reading.unit == 0)
        .order_by(Reading.record_date)
        .all()
    )
    db.close()

    results = []
    for stmt in stmts:
        end_month = stmt.period_end_month or stmt.billing_month
        end_year = stmt.period_end_year or stmt.billing_year

        period_start = date_type(stmt.billing_year, stmt.billing_month, 1)
        if end_month == 12:
            period_end = date_type(end_year + 1, 1, 1)
        else:
            period_end = date_type(end_year, end_month + 1, 1)

        before_start = [r for r in main_readings if r.record_date.date() <= period_start]
        before_end = [r for r in main_readings if r.record_date.date() < period_end]

        main_meter_kl = None
        if before_start and before_end:
            baseline = before_start[-1]
            end_rdg = before_end[-1]
            if baseline.id != end_rdg.id:
                main_meter_kl = round(max(0.0, end_rdg.reading - baseline.reading), 3)

        discrepancy_kl = round(stmt.total_consumption_kl - main_meter_kl, 3) if main_meter_kl is not None else None

        results.append({
            "billing_statement_id": stmt.id,
            "billing_month": stmt.billing_month,
            "billing_year": stmt.billing_year,
            "period_end_month": end_month,
            "period_end_year": end_year,
            "total_consumption_kl": stmt.total_consumption_kl,
            "billing_cost_aud": stmt.billing_cost_aud,
            "main_meter_kl": main_meter_kl,
            "discrepancy_kl": discrepancy_kl,
            "has_sufficient_readings": main_meter_kl is not None,
        })

    return results


def compute_median_interval(values: list) -> float:
    if len(values) < 2:
        return 1.0
    gaps = [(values[i][0] - values[i - 1][0]).days for i in range(1, len(values))]
    return median(gaps) if gaps else 1.0

# Detect anomalies in usage
@app.get("/anomalies")
async def detect_anomalies():
    db = SessionLocal()
    rows = db.query(Reading).all()
    db.close()

    data = defaultdict(list)

    for r in rows:
        data[r.mi].append((r.record_date, r.reading))

    anomalies = []

    for household, values in data.items():
        if len(values) < 3:
            continue

        values.sort(key=lambda x: x[0])
        med_interval = compute_median_interval(values)

        for i in range(2, len(values)):
            prev_usage = values[i - 1][1] - values[i - 2][1]
            curr_usage = values[i][1] - values[i - 1][1]

            if prev_usage <= 0:
                continue

            pct = ((curr_usage - prev_usage) / prev_usage) * 100

            if pct > 150:
                gap_days = (values[i][0] - values[i - 1][0]).days
                anomalies.append({
                    "household": household,
                    "previous_usage": round(prev_usage, 4),
                    "current_usage": round(curr_usage, 4),
                    "increase_percent": round(pct, 2),
                    "reading_date": values[i][0].isoformat(),
                    "gap_days": gap_days,
                    "median_interval_days": round(med_interval, 1),
                    "is_gap_induced": gap_days > GAP_MULTIPLIER * med_interval,
                })

    return anomalies
