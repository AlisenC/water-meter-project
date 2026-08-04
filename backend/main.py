from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
import csv
import os
import base64
import json
import re
from io import StringIO
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .database import SessionLocal, engine
from .models import Base, Reading, BillingStatement
from datetime import datetime, date as date_type
from pydantic import BaseModel
from typing import Optional
from collections import defaultdict
from statistics import median
from .ai_agent import router as ai_router
from .oracle_ai import router as oracle_router
from . import csv_parser
import anthropic as anthropic_sdk

GAP_MULTIPLIER = 1.5

_GALLONS_PER_UNIT = 0.748
DISCREPANCY_TOLERANCE_UNITS = 1.0  # ~748 gallons; a statement/household-sum pair within this is considered "matching"
# What 748 gallons would have converted to under the old (mislabeled) "kilolitres" constant —
# used only by the one-time migration below to guess whether legacy data needs converting.
_LEGACY_KL_PER_UNIT = 0.748 * 0.00378541


def _to_units(reading: float, unit: int) -> float:
    return reading if unit == 1 else reading / _GALLONS_PER_UNIT


def _household_sum_units(readings_by_mi: dict, billing_month: int, billing_year: int,
                          period_end_month: int | None, period_end_year: int | None) -> float | None:
    """Sum of household meter deltas for a billing period, in units of water. None if insufficient data."""
    end_month = period_end_month or billing_month
    end_year = period_end_year or billing_year
    period_start = date_type(billing_year, billing_month, 1)
    period_end = date_type(end_year + 1, 1, 1) if end_month == 12 else date_type(end_year, end_month + 1, 1)

    total = 0.0
    has_data = False
    for rows in readings_by_mi.values():
        before_start = [r for r in rows if r[0].date() <= period_start]
        before_end = [r for r in rows if r[0].date() < period_end]
        if not before_start or not before_end:
            continue
        baseline = before_start[-1]
        end_rdg = before_end[-1]
        if baseline[0] == end_rdg[0]:
            continue
        total += max(0.0, _to_units(end_rdg[1], end_rdg[2]) - _to_units(baseline[1], baseline[2]))
        has_data = True
    return round(total, 3) if has_data else None


def _migrate_billing_statements_schema():
    """
    One-time migration for deployments that already have billing_statements rows under
    the old (mislabeled) schema — total_consumption_kl / billing_cost_aud. Adds the new
    columns and backfills them without dropping the old ones, so a deployed volume's data
    survives this schema change rather than needing to be wiped.

    The old extraction prompt asked the AI for "kilolitres," but real US water bills don't
    print kL — they print "units of water." So an old row's stored number is most likely
    already a units-of-water figure under a wrong label, not a true kL conversion. Since we
    can't know for certain which it was, we cross-check each row against the actual summed
    household meter deltas for that billing period (when available) and pick whichever
    interpretation — as-is, or divided by the old kL-per-unit constant — lands closer to
    that independent reference. Falls back to "as-is" when there's no reading data to check
    against.
    """
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(billing_statements)"))}
        if not cols or "total_units_consumed" in cols or "total_consumption_kl" not in cols:
            return  # no table yet (create_all will make one), or already migrated

        conn.execute(text("ALTER TABLE billing_statements ADD COLUMN total_units_consumed FLOAT"))
        conn.execute(text("ALTER TABLE billing_statements ADD COLUMN total_cost FLOAT"))
        conn.execute(text("ALTER TABLE billing_statements ADD COLUMN cost_per_unit FLOAT"))
        conn.commit()

        old_rows = conn.execute(text(
            "SELECT id, billing_month, billing_year, period_end_month, period_end_year,"
            " total_consumption_kl, billing_cost_aud FROM billing_statements"
        )).fetchall()
        reading_rows = conn.execute(text("SELECT mi, reading, record_date, unit FROM readings")).fetchall()

    readings_by_mi = defaultdict(list)
    for mi, reading, record_date, unit in reading_rows:
        if mi == "MAIN":
            continue
        readings_by_mi[mi].append((datetime.fromisoformat(record_date), reading, unit))
    for rows in readings_by_mi.values():
        rows.sort(key=lambda r: r[0])

    with engine.connect() as conn:
        for row_id, b_month, b_year, pe_month, pe_year, old_kl, old_aud in old_rows:
            as_is = old_kl
            converted = old_kl / _LEGACY_KL_PER_UNIT
            reference = _household_sum_units(readings_by_mi, b_month, b_year, pe_month, pe_year)

            if reference:
                total_units_consumed = as_is if abs(as_is - reference) <= abs(converted - reference) else converted
            else:
                total_units_consumed = as_is

            total_cost = old_aud
            cost_per_unit = round(total_cost / total_units_consumed, 4) if total_units_consumed else None

            conn.execute(
                text(
                    "UPDATE billing_statements SET total_units_consumed = :u, total_cost = :c,"
                    " cost_per_unit = :cpu WHERE id = :id"
                ),
                {"u": total_units_consumed, "c": total_cost, "cpu": cost_per_unit, "id": row_id},
            )
        conn.commit()


_migrate_billing_statements_schema()

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)
app = FastAPI()

class ReadingCreate(BaseModel):
    mi: str
    reading: float

# AI Agent Router
app.include_router(ai_router, prefix="/ai")

# Oracle 26ai Router
app.include_router(oracle_router)

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
async def add_reading(data: ReadingCreate):
    db = SessionLocal()

    new_reading = Reading(
        mi=data.mi,
        reading=data.reading,
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
            errors.append({"row_num": row_num, "reason": "parse_error", "raw_value": str(e)})
            skipped += 1

    db.commit()
    db.close()

    return {"inserted": inserted, "skipped": skipped, "errors": errors}

class FilePreview(BaseModel):
    filename: str
    detected_format: str
    total_rows: int
    valid_rows: int
    error_rows: int
    rows_after_filter: int
    households_found: list[str]
    households_after_filter: list[str]
    date_min: Optional[str]
    date_max: Optional[str]
    errors: list[dict]


class ImportPreviewResponse(BaseModel):
    files: list[FilePreview]
    total_rows_to_import: int
    total_errors: int
    all_households: list[str]


def _build_existing_units(db) -> dict[str, int]:
    rows = db.query(Reading.mi, Reading.unit).distinct().all()
    result = {}
    for mi, unit in rows:
        if mi not in result:
            result[mi] = unit
    return result


def _parse_date_form(value: Optional[str]) -> Optional[date_type]:
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        return None


def _build_file_preview(
    file_bytes: bytes,
    filename: str,
    existing_units: dict[str, int],
    date_start: Optional[date_type],
    date_end: Optional[date_type],
    exclude_households: list[str],
    fmt_override: Optional[str],
) -> FilePreview:
    try:
        fmt_key, valid_rows, error_rows = csv_parser.parse_csv_bytes(
            file_bytes, filename, existing_units, fmt_override
        )
    except ValueError as e:
        return FilePreview(
            filename=filename,
            detected_format="unknown",
            total_rows=0,
            valid_rows=0,
            error_rows=1,
            rows_after_filter=0,
            households_found=[],
            households_after_filter=[],
            date_min=None,
            date_max=None,
            errors=[{"row_num": 0, "reason": "format_error", "raw_value": str(e), "filename": filename}],
        )

    included, _ = csv_parser.apply_filters(valid_rows, date_start, date_end, exclude_households)

    households_found = sorted({r["mi"] for r in valid_rows})
    households_after = sorted({r["mi"] for r in included})
    dates = [r["record_date"] for r in valid_rows]
    date_min = min(dates).isoformat() if dates else None
    date_max = max(dates).isoformat() if dates else None

    return FilePreview(
        filename=filename,
        detected_format=fmt_key,
        total_rows=len(valid_rows) + len(error_rows),
        valid_rows=len(valid_rows),
        error_rows=len(error_rows),
        rows_after_filter=len(included),
        households_found=households_found,
        households_after_filter=households_after,
        date_min=date_min,
        date_max=date_max,
        errors=error_rows,
    )


@app.post("/import-csv/v2/preview")
async def import_csv_v2_preview(
    files: list[UploadFile] = File(...),
    date_start: Optional[str] = Form(default=None),
    date_end: Optional[str] = Form(default=None),
    exclude_households: str = Form(default=""),
    fmt_override: Optional[str] = Form(default=None),
) -> ImportPreviewResponse:
    db = SessionLocal()
    existing_units = _build_existing_units(db)
    db.close()

    ds = _parse_date_form(date_start)
    de = _parse_date_form(date_end)
    exclusions = [h.strip() for h in exclude_households.split(",") if h.strip()]
    override = fmt_override if fmt_override in ("A", "B", "C") else None

    file_previews = []
    for upload in files:
        file_bytes = await upload.read()
        fp = _build_file_preview(file_bytes, upload.filename, existing_units, ds, de, exclusions, override)
        file_previews.append(fp)

    all_households = sorted({h for fp in file_previews for h in fp.households_after_filter})
    return ImportPreviewResponse(
        files=file_previews,
        total_rows_to_import=sum(fp.rows_after_filter for fp in file_previews),
        total_errors=sum(fp.error_rows for fp in file_previews),
        all_households=all_households,
    )


@app.post("/import-csv/v2/confirm")
async def import_csv_v2_confirm(
    files: list[UploadFile] = File(...),
    date_start: Optional[str] = Form(default=None),
    date_end: Optional[str] = Form(default=None),
    exclude_households: str = Form(default=""),
    fmt_override: Optional[str] = Form(default=None),
):
    db = SessionLocal()
    existing_units = _build_existing_units(db)

    ds = _parse_date_form(date_start)
    de = _parse_date_form(date_end)
    exclusions = [h.strip() for h in exclude_households.split(",") if h.strip()]
    override = fmt_override if fmt_override in ("A", "B", "C") else None

    total_inserted = 0
    total_skipped = 0
    all_errors: list[dict] = []
    per_file = []

    for upload in files:
        file_bytes = await upload.read()
        try:
            _, valid_rows, error_rows = csv_parser.parse_csv_bytes(
                file_bytes, upload.filename, existing_units, override
            )
        except ValueError as e:
            err = {"row_num": 0, "reason": "format_error", "raw_value": str(e), "filename": upload.filename}
            all_errors.append(err)
            per_file.append({"filename": upload.filename, "inserted": 0, "skipped": 0})
            continue

        included, _ = csv_parser.apply_filters(valid_rows, ds, de, exclusions)
        skipped = len(valid_rows) - len(included) + len(error_rows)

        for row in included:
            db.add(Reading(
                mi=row["mi"],
                reading=row["reading"],
                record_date=datetime.combine(row["record_date"], datetime.min.time()),
                unit=row["unit"],
            ))

        all_errors.extend(error_rows)
        total_inserted += len(included)
        total_skipped += skipped
        per_file.append({"filename": upload.filename, "inserted": len(included), "skipped": skipped})

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        db.close()
        raise HTTPException(status_code=500, detail=f"Database write failed: {e}")
    db.close()

    return {
        "inserted": total_inserted,
        "skipped": total_skipped,
        "errors": all_errors,
        "per_file": per_file,
    }


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
  "total_units_consumed": <float, units of water>,
  "total_cost": <float, total amount due in USD>
}
Rules:
- total_units_consumed: the "total consumption in units of water" figure as printed on the statement (1 unit of water = 748 gallons). Report the number exactly as printed — do not convert it to gallons, cubic feet, or any other unit.
- total_cost: the total amount due for this bill, in US dollars, no currency symbol.
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
        "total_units_consumed", "total_cost",
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

    total_units_consumed = float(extracted["total_units_consumed"])
    total_cost = float(extracted["total_cost"])
    cost_per_unit = round(total_cost / total_units_consumed, 4) if total_units_consumed else None

    stmt = BillingStatement(
        billing_month=start_month,
        billing_year=start_year,
        period_end_month=int(extracted["billing_period_end_month"]),
        period_end_year=int(extracted["billing_period_end_year"]),
        total_units_consumed=total_units_consumed,
        total_cost=total_cost,
        cost_per_unit=cost_per_unit,
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
        "total_units_consumed": stmt.total_units_consumed,
        "total_cost": stmt.total_cost,
        "cost_per_unit": stmt.cost_per_unit,
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
            "total_units_consumed": s.total_units_consumed,
            "total_cost": s.total_cost,
            "cost_per_unit": s.cost_per_unit,
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


# Verify billing statements against summed household meter readings
@app.get("/billing-verify")
async def billing_verify():
    db = SessionLocal()
    stmts = db.query(BillingStatement).order_by(
        BillingStatement.billing_year,
        BillingStatement.billing_month,
    ).all()
    all_readings = db.query(Reading).order_by(Reading.record_date).all()
    db.close()

    # Group readings by household (exclude the main/master meter, if present, to avoid double-counting)
    by_mi: dict[str, list] = defaultdict(list)
    for r in all_readings:
        if r.mi == "MAIN":
            continue
        by_mi[r.mi].append(r)

    results = []
    for stmt in stmts:
        end_month = stmt.period_end_month or stmt.billing_month
        end_year = stmt.period_end_year or stmt.billing_year

        period_start = date_type(stmt.billing_year, stmt.billing_month, 1)
        if end_month == 12:
            period_end = date_type(end_year + 1, 1, 1)
        else:
            period_end = date_type(end_year, end_month + 1, 1)

        household_sum_units = 0.0
        has_any_data = False

        for readings in by_mi.values():
            before_start = [r for r in readings if r.record_date.date() <= period_start]
            before_end = [r for r in readings if r.record_date.date() < period_end]
            if not before_start or not before_end:
                continue
            baseline = before_start[-1]
            end_rdg = before_end[-1]
            if baseline.id == end_rdg.id:
                continue
            household_sum_units += max(0.0, _to_units(end_rdg.reading, end_rdg.unit) - _to_units(baseline.reading, baseline.unit))
            has_any_data = True

        household_sum_units = round(household_sum_units, 3) if has_any_data else None
        discrepancy_units = round(stmt.total_units_consumed - household_sum_units, 3) if household_sum_units is not None else None
        money_lost = (
            round(discrepancy_units * stmt.cost_per_unit, 2)
            if discrepancy_units is not None and stmt.cost_per_unit is not None
            else None
        )

        results.append({
            "billing_statement_id": stmt.id,
            "billing_month": stmt.billing_month,
            "billing_year": stmt.billing_year,
            "period_end_month": end_month,
            "period_end_year": end_year,
            "total_units_consumed": stmt.total_units_consumed,
            "total_cost": stmt.total_cost,
            "cost_per_unit": stmt.cost_per_unit,
            "household_sum_units": household_sum_units,
            "discrepancy_units": discrepancy_units,
            "money_lost": money_lost,
            "has_sufficient_readings": has_any_data,
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
