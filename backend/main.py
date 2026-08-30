from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
import os
import base64
import json
import re
from io import BytesIO
from fastapi.middleware.cors import CORSMiddleware
from .database import SessionLocal
from .models import Reading, BillingStatement
from datetime import datetime, date as date_type
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.exc import IntegrityError
from collections import defaultdict
from .ai_agent import router as ai_router
from .oracle_ai import router as oracle_router
from .leak_detection import router as leak_router
from . import csv_parser, leak_rules
from .units import to_units as _to_units
import anthropic as anthropic_sdk
import httpx
from pypdf import PdfReader, PdfWriter

DISCREPANCY_TOLERANCE_UNITS = 1.0  # ~748 gallons; a statement/household-sum pair within this is considered "matching"


def _household_sum_units(readings_by_mi: dict, billing_month: int, billing_year: int,
                          period_end_month: int | None, period_end_year: int | None) -> float | None:
    """Sum of household meter deltas for a billing period, in units of water.

    Exclusive upper bounds: a reading taken during the boundary month itself still counts
    as a valid baseline/endpoint, since bills only give month-level granularity but real
    meter reads land mid-month — a strict "before day 1" cutoff would skip the correct
    reading and fall back a full extra cycle, inflating the result.

    Args:
        readings_by_mi: Meter ID -> list of (datetime, reading, unit) tuples, sorted ascending by datetime.
        billing_month: Start month of the billing period (1-12).
        billing_year: Start year of the billing period.
        period_end_month: End month of the period if different from the start; None to use billing_month.
        period_end_year: End year of the period if different from the start; None to use billing_year.

    Returns:
        Total units of water consumed across all households in the period, rounded to 3
        decimals, or None if no household had a reading before both the period start and end.
    """
    end_month = period_end_month or billing_month
    end_year = period_end_year or billing_year
    period_start_end_excl = date_type(billing_year + 1, 1, 1) if billing_month == 12 else date_type(billing_year, billing_month + 1, 1)
    period_end = date_type(end_year + 1, 1, 1) if end_month == 12 else date_type(end_year, end_month + 1, 1)

    total = 0.0
    has_data = False
    for rows in readings_by_mi.values():
        before_start = [r for r in rows if r[0].date() < period_start_end_excl]
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


app = FastAPI()

class ReadingCreate(BaseModel):
    mi: str
    reading: float

class BillingStatementUpdate(BaseModel):
    total_units_consumed: Optional[float] = None
    total_cost: Optional[float] = None
    billing_month: Optional[int] = None
    billing_year: Optional[int] = None
    period_end_month: Optional[int] = None
    period_end_year: Optional[int] = None

# AI Agent Router
app.include_router(ai_router, prefix="/ai")

# Oracle 26ai Router
app.include_router(oracle_router)

# Daily Leak Detection Router
app.include_router(leak_router, prefix="/leak")

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
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.close()
        raise HTTPException(status_code=409, detail="A reading for this meter at this exact timestamp already exists.")
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


class ConflictRow(BaseModel):
    row_num: int
    filename: str
    mi: str
    record_date: str
    existing_id: Optional[int]  # None for an in-batch conflict never yet written to the DB
    existing_reading: float
    existing_unit: int
    new_reading: float
    new_unit: int


class ConflictResolution(BaseModel):
    id: int
    reading: float
    unit: int


class ResolveConflictsRequest(BaseModel):
    resolutions: list[ConflictResolution]


class FilePreview(BaseModel):
    filename: str
    detected_format: str
    total_rows: int
    valid_rows: int
    error_rows: int
    duplicate_rows: int
    conflict_rows: int
    rows_after_filter: int
    households_found: list[str]
    households_after_filter: list[str]
    date_min: Optional[str]
    date_max: Optional[str]
    errors: list[dict]
    conflicts: list[ConflictRow]


class ImportPreviewResponse(BaseModel):
    files: list[FilePreview]
    total_rows_to_import: int
    total_errors: int
    total_duplicates: int
    total_conflicts: int
    all_households: list[str]


def _build_existing_units(db) -> dict[str, int]:
    rows = db.query(Reading.mi, Reading.unit).distinct().all()
    result = {}
    for mi, unit in rows:
        if mi not in result:
            result[mi] = unit
    return result


def _build_existing_reading_keys(db) -> dict[tuple[str, date_type], dict]:
    rows = db.query(Reading.id, Reading.mi, Reading.record_date, Reading.reading, Reading.unit).all()
    result = {}
    for id_, mi, record_date, reading, unit in rows:
        result[(mi, record_date.date())] = {"id": id_, "reading": reading, "unit": unit}
    return result


def _serialize_conflict_row(row: dict, filename: str) -> ConflictRow:
    return ConflictRow(
        row_num=row["row_num"],
        filename=filename,
        mi=row["mi"],
        record_date=row["record_date"].isoformat(),
        existing_id=row["existing_id"],
        existing_reading=row["existing_reading"],
        existing_unit=row["existing_unit"],
        new_reading=row["reading"],
        new_unit=row["unit"],
    )


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
    existing_keys: dict[tuple[str, date_type], dict],
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
            duplicate_rows=0,
            conflict_rows=0,
            rows_after_filter=0,
            households_found=[],
            households_after_filter=[],
            date_min=None,
            date_max=None,
            errors=[{"row_num": 0, "reason": "format_error", "raw_value": str(e), "filename": filename}],
            conflicts=[],
        )

    included, excluded = csv_parser.apply_filters(valid_rows, date_start, date_end, exclude_households, existing_keys)

    duplicate_count = sum(1 for r in excluded if r["filter_reason"] == "duplicate")
    conflicts = [_serialize_conflict_row(r, filename) for r in excluded if r["filter_reason"] == "conflict"]

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
        duplicate_rows=duplicate_count,
        conflict_rows=len(conflicts),
        rows_after_filter=len(included),
        households_found=households_found,
        households_after_filter=households_after,
        date_min=date_min,
        date_max=date_max,
        errors=error_rows,
        conflicts=conflicts,
    )


@app.post("/import-csv/preview")
async def import_csv_preview(
    files: list[UploadFile] = File(...),
    date_start: Optional[str] = Form(default=None),
    date_end: Optional[str] = Form(default=None),
    exclude_households: str = Form(default=""),
    fmt_override: Optional[str] = Form(default=None),
) -> ImportPreviewResponse:
    db = SessionLocal()
    existing_units = _build_existing_units(db)
    existing_keys = _build_existing_reading_keys(db)
    db.close()

    ds = _parse_date_form(date_start)
    de = _parse_date_form(date_end)
    exclusions = [h.strip() for h in exclude_households.split(",") if h.strip()]
    override = fmt_override if fmt_override in ("A", "B", "C") else None

    file_previews = []
    for upload in files:
        file_bytes = await upload.read()
        fp = _build_file_preview(file_bytes, upload.filename, existing_units, existing_keys, ds, de, exclusions, override)
        file_previews.append(fp)

    all_households = sorted({h for fp in file_previews for h in fp.households_after_filter})
    return ImportPreviewResponse(
        files=file_previews,
        total_rows_to_import=sum(fp.rows_after_filter for fp in file_previews),
        total_errors=sum(fp.error_rows for fp in file_previews),
        total_duplicates=sum(fp.duplicate_rows for fp in file_previews),
        total_conflicts=sum(fp.conflict_rows for fp in file_previews),
        all_households=all_households,
    )


@app.post("/import-csv/confirm")
async def import_csv_confirm(
    files: list[UploadFile] = File(...),
    date_start: Optional[str] = Form(default=None),
    date_end: Optional[str] = Form(default=None),
    exclude_households: str = Form(default=""),
    fmt_override: Optional[str] = Form(default=None),
):
    db = SessionLocal()
    existing_units = _build_existing_units(db)
    existing_keys = _build_existing_reading_keys(db)

    ds = _parse_date_form(date_start)
    de = _parse_date_form(date_end)
    exclusions = [h.strip() for h in exclude_households.split(",") if h.strip()]
    override = fmt_override if fmt_override in ("A", "B", "C") else None

    total_inserted = 0
    total_skipped = 0
    total_duplicates = 0
    total_conflicts = 0
    all_errors: list[dict] = []
    all_conflicts: list[ConflictRow] = []
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
            per_file.append({"filename": upload.filename, "inserted": 0, "skipped": 0, "duplicates": 0, "conflicts": 0})
            continue

        included, excluded = csv_parser.apply_filters(valid_rows, ds, de, exclusions, existing_keys)
        duplicate_rows = [r for r in excluded if r["filter_reason"] == "duplicate"]
        conflict_rows = [_serialize_conflict_row(r, upload.filename) for r in excluded if r["filter_reason"] == "conflict"]
        skipped = len(excluded) + len(error_rows)

        for row in included:
            db.add(Reading(
                mi=row["mi"],
                reading=row["reading"],
                record_date=datetime.combine(row["record_date"], datetime.min.time()),
                unit=row["unit"],
            ))

        all_errors.extend(error_rows)
        all_conflicts.extend(conflict_rows)
        total_inserted += len(included)
        total_skipped += skipped
        total_duplicates += len(duplicate_rows)
        total_conflicts += len(conflict_rows)
        per_file.append({
            "filename": upload.filename,
            "inserted": len(included),
            "skipped": skipped,
            "duplicates": len(duplicate_rows),
            "conflicts": len(conflict_rows),
        })

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.close()
        raise HTTPException(status_code=409, detail="Import conflicts with a concurrent write to the readings table. Retry the import.")
    except Exception as e:
        db.rollback()
        db.close()
        raise HTTPException(status_code=500, detail=f"Database write failed: {e}")
    db.close()

    return {
        "inserted": total_inserted,
        "skipped": total_skipped,
        "duplicates": total_duplicates,
        "conflicts": total_conflicts,
        "errors": all_errors,
        "conflict_rows": all_conflicts,
        "per_file": per_file,
    }


# Resolve one or more flagged CSV-import conflicts by overwriting the existing row's
# reading/unit in place with the imported value — an alternative to manually finding
# and deleting the offending row via DELETE /readings/{id}. Update-in-place (not
# delete+reinsert) keeps the row's id and its unique-key match stable throughout.
@app.post("/readings/resolve-conflicts")
async def resolve_conflicts(data: ResolveConflictsRequest):
    db = SessionLocal()
    not_found = []
    updated = 0
    for r in data.resolutions:
        result = db.query(Reading).filter(Reading.id == r.id).update(
            {"reading": r.reading, "unit": r.unit}, synchronize_session=False
        )
        if result:
            updated += 1
        else:
            not_found.append(r.id)
    db.commit()
    db.close()
    return {"updated": updated, "not_found": not_found}


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

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

# Oracle wallet files persist in the Docker volume via DATA_DIR=/app/data (see oracle_ai.py's WALLET_DIR).
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


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
- billing_period_start_month/year and billing_period_end_month/year: the start and end of the service/billing period this bill covers. Water bills usually print this as a date range, e.g. "Service from 11/15/2024 to 01/14/2025", a "Billing Period" line, or a meter reading section with a previous-reading date and a current-reading date — use those two dates' months/years. Do not use the bill date or payment due date for these fields.
- total_units_consumed: the "total consumption in units of water" figure as printed on the statement (1 unit of water = 748 gallons). Report the number exactly as printed — do not convert it to gallons, cubic feet, or any other unit.
- total_cost: the total amount due for this bill, in US dollars, no currency symbol.
- Use null for any field that cannot be determined.
- Return only the JSON object. No other text."""


def _parse_ai_json(raw_text: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw_text, re.IGNORECASE)
    cleaned = match.group(1).strip() if match else raw_text.strip()
    return json.loads(cleaned)


_NUMBER_RE = re.compile(r"\d[\d,]*\.?\d*")
_SLASH_DATE_RE = re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b")


def _normalize_number(value) -> str:
    f = float(value)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _source_number_tokens(source_text: str) -> set[str]:
    """Every number printed in the statement text, normalized for comparison. Used to
    catch a model transcription error (e.g. a doubled digit dropped: 117 -> 17) by
    checking the extracted value was actually printed, rather than trusting the model
    reproduced it correctly."""
    tokens = set()
    for m in _NUMBER_RE.finditer(source_text):
        raw = m.group(0).replace(",", "").strip(".")
        if not raw:
            continue
        try:
            tokens.add(_normalize_number(raw))
        except ValueError:
            continue
    return tokens


def _normalize_year(raw: str) -> int:
    if len(raw) == 4:
        return int(raw)
    y = int(raw)
    return 2000 + y if y < 70 else 1900 + y


def _date_in_source_text(source_text: str, month: int, year: int) -> bool | None:
    """Checks whether any MM/DD/YYYY-style date in the text, for the given year, has
    `month` as one of its numeric components. Scoped by year (not just "does this
    number appear in some date somewhere") because with a start and an end date both
    present, an unscoped check lets a dropped digit collide with the other date's day
    or month field and slip through undetected. Returns None (verification skipped) if
    the text has no dates for that year at all, since some statements only spell dates
    out ("November 15, 2024"), where this check can't say anything either way."""
    scoped = [
        (int(m1), int(m2))
        for m1, m2, y in _SLASH_DATE_RE.findall(source_text)
        if _normalize_year(y) == year
    ]
    if not scoped:
        return None
    return any(month in (m1, m2) for m1, m2 in scoped)


def _verify_extraction(source_text: str, extracted: dict) -> list[str]:
    """Returns the names of extracted fields that could not be confirmed against the
    statement's own text — a signal (not proof) that the AI mistyped a number or date,
    which the local Ollama model in particular is prone to on repeated/doubled digits."""
    if not source_text:
        return []

    warnings = []
    number_tokens = _source_number_tokens(source_text)

    for field in ("total_units_consumed", "total_cost"):
        value = extracted.get(field)
        if value is None:
            continue
        try:
            if _normalize_number(value) not in number_tokens:
                warnings.append(field)
        except (TypeError, ValueError):
            warnings.append(field)

    for month_field, year_field in (
        ("billing_period_start_month", "billing_period_start_year"),
        ("billing_period_end_month", "billing_period_end_year"),
    ):
        month, year = extracted.get(month_field), extracted.get(year_field)
        if month is None or year is None:
            continue
        if _date_in_source_text(source_text, int(month), int(year)) is False:
            warnings.append(month_field)

    return warnings


def _first_page_reader(pdf_bytes: bytes) -> PdfReader:
    """Statements are sometimes followed by a payment stub, terms/conditions insert, or a
    second account's pages — only page 1 is ever the actual bill, so extraction always
    operates on that page alone rather than the whole (possibly multi-page) upload."""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read this PDF (it may be corrupted or encrypted): {e}")
    if not reader.pages:
        raise HTTPException(status_code=422, detail="This PDF has no pages.")
    return reader


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = _first_page_reader(pdf_bytes)
    try:
        text = reader.pages[0].extract_text() or ""
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read this PDF (it may be corrupted or encrypted): {e}")
    return text.strip()


def _first_page_pdf_bytes(pdf_bytes: bytes) -> bytes:
    """Trims the upload down to page 1 before handing it to a cloud provider, so a
    multi-page statement (payment stub, inserts, etc.) doesn't confuse extraction."""
    reader = _first_page_reader(pdf_bytes)
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _extract_with_ollama(pdf_bytes: bytes, filename: str) -> str:
    text = _extract_pdf_text(pdf_bytes)
    if not text:
        raise HTTPException(
            status_code=422,
            detail="This PDF has no extractable text layer (likely a scanned/image-only document). "
                   "Configure an Anthropic or OpenAI API key in Settings to import it.",
        )

    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": f"{EXTRACTION_PROMPT}\n\nStatement text:\n{text}"}],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=120.0,
        )
    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not reach Ollama at {OLLAMA_BASE_URL}. Start Ollama (`ollama serve`) "
                   "or configure an Anthropic/OpenAI API key in Settings.",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {e}") from e

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama returned HTTP {response.status_code}: {response.text[:300]}")

    try:
        body = response.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail=f"Ollama returned a non-JSON response: {response.text[:300]}") from e

    return body.get("message", {}).get("content", "")


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


def _extract_billing_data(pdf_bytes: bytes, filename: str, x_api_key: str | None, x_api_provider: str | None) -> dict:
    """Runs AI extraction and parses/validates the result. Raises HTTPException on any
    failure (unreadable PDF, provider error, non-JSON response, missing required
    field) — the caller is responsible for deciding what happens on failure."""
    try:
        if not x_api_key:
            raw_text = _extract_with_ollama(pdf_bytes, filename)
        else:
            pdf_b64 = base64.standard_b64encode(_first_page_pdf_bytes(pdf_bytes)).decode("utf-8")
            provider = (x_api_provider or "anthropic").lower()
            if provider == "openai":
                raw_text = _extract_with_openai(pdf_b64, filename, x_api_key)
            else:
                raw_text = _extract_with_anthropic(pdf_b64, filename, x_api_key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI extraction failed: {str(e)}")

    try:
        extracted = _parse_ai_json(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail=f"AI returned non-JSON response: {raw_text[:300]}")

    try:
        source_text = _extract_pdf_text(pdf_bytes)
    except HTTPException:
        source_text = ""  # e.g. a scanned PDF handled by a cloud provider's vision input — nothing to verify against
    low_confidence_fields = _verify_extraction(source_text, extracted)

    # Only the period start is truly required (it's the dedup/identity key below). Every
    # other field is best-effort: rather than failing the whole import when the model
    # misses one, leave it blank (None) and let the statement still get created —
    # total_units_consumed and total_cost are editable afterward in the UI for exactly
    # this reason, so the user can review and fill in whatever the AI couldn't read.
    if extracted.get("billing_period_start_month") is None or extracted.get("billing_period_start_year") is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not determine the billing period start date, which is required to import a statement. Raw AI response: {raw_text[:300]}",
        )

    start_month = int(extracted["billing_period_start_month"])
    start_year = int(extracted["billing_period_start_year"])
    end_month = int(extracted["billing_period_end_month"]) if extracted.get("billing_period_end_month") is not None else start_month
    end_year = int(extracted["billing_period_end_year"]) if extracted.get("billing_period_end_year") is not None else start_year
    total_units_consumed = float(extracted["total_units_consumed"]) if extracted.get("total_units_consumed") is not None else None
    total_cost = float(extracted["total_cost"]) if extracted.get("total_cost") is not None else None

    return {
        "start_month": start_month,
        "start_year": start_year,
        "end_month": end_month,
        "end_year": end_year,
        "total_units_consumed": total_units_consumed,
        "total_cost": total_cost,
        "low_confidence_fields": low_confidence_fields,
    }


def _create_stub_statement(filename: str | None = None, reason: str | None = None) -> dict:
    """Create a blank, needs_review statement for the user to fill in through the
    normal editing UI (StatementsList) — either as a fallback for a PDF that failed
    automatic extraction (unreadable/encrypted PDF, no text layer, AI provider error,
    non-JSON response, or no billing period found), so the upload isn't discarded
    outright, or as a manually-added blank row with no upload at all."""
    db = SessionLocal()
    stmt = BillingStatement(
        billing_month=None,
        billing_year=None,
        period_end_month=None,
        period_end_year=None,
        total_units_consumed=None,
        total_cost=None,
        cost_per_unit=None,
        source_filename=filename,
        imported_at=datetime.utcnow(),
        needs_review=True,
    )
    db.add(stmt)
    db.commit()
    db.refresh(stmt)
    stmt_id = stmt.id
    db.close()

    return {
        "id": stmt_id,
        "billing_month": None,
        "billing_year": None,
        "period_end_month": None,
        "period_end_year": None,
        "total_units_consumed": None,
        "total_cost": None,
        "cost_per_unit": None,
        "source_filename": filename,
        "needs_review": True,
        "review_reason": reason,
        "low_confidence_fields": [],
    }


# Import a billing statement PDF
@app.post("/import-billing")
async def import_billing(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
    x_api_provider: str | None = Header(default=None),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes = await file.read()

    try:
        extraction = _extract_billing_data(pdf_bytes, file.filename, x_api_key, x_api_provider)
    except HTTPException as e:
        return _create_stub_statement(file.filename, str(e.detail))

    start_month, start_year = extraction["start_month"], extraction["start_year"]
    end_month, end_year = extraction["end_month"], extraction["end_year"]
    total_units_consumed, total_cost = extraction["total_units_consumed"], extraction["total_cost"]
    low_confidence_fields = extraction["low_confidence_fields"]

    db = SessionLocal()
    existing = db.query(BillingStatement).filter(
        BillingStatement.billing_month == start_month,
        BillingStatement.billing_year == start_year,
    ).first()
    if existing:
        db.close()
        raise HTTPException(status_code=409, detail=f"A statement for {start_month}/{start_year} already exists (id={existing.id}).")

    cost_per_unit = round(total_cost / total_units_consumed, 4) if total_units_consumed and total_cost is not None else None

    stmt = BillingStatement(
        billing_month=start_month,
        billing_year=start_year,
        period_end_month=end_month,
        period_end_year=end_year,
        total_units_consumed=total_units_consumed,
        total_cost=total_cost,
        cost_per_unit=cost_per_unit,
        source_filename=file.filename,
        imported_at=datetime.utcnow(),
        needs_review=False,
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
        "needs_review": stmt.needs_review,
        "low_confidence_fields": low_confidence_fields,
    }


# Manually add a blank billing statement for the user to fill in themselves
@app.post("/billing-statements")
async def create_blank_billing_statement():
    return _create_stub_statement()


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
            "needs_review": s.needs_review,
        }
        for s in stmts
    ]


# Manually correct a billing statement's units/cost/dates — e.g. after an AI extraction
# that missed, misread, or (per the local Ollama model's known weakness) dropped a
# repeated digit in these fields.
@app.patch("/billing-statements/{stmt_id}")
async def update_billing_statement(stmt_id: int, data: BillingStatementUpdate):
    if data.total_units_consumed is not None and data.total_units_consumed < 0:
        raise HTTPException(status_code=422, detail="total_units_consumed cannot be negative.")
    if data.total_cost is not None and data.total_cost < 0:
        raise HTTPException(status_code=422, detail="total_cost cannot be negative.")
    for field in ("billing_month", "period_end_month"):
        value = getattr(data, field)
        if value is not None and not (1 <= value <= 12):
            raise HTTPException(status_code=422, detail=f"{field} must be between 1 and 12.")
    for field in ("billing_year", "period_end_year"):
        value = getattr(data, field)
        if value is not None and value < 2000:
            raise HTTPException(status_code=422, detail=f"{field} must be a plausible 4-digit year.")

    db = SessionLocal()
    stmt = db.query(BillingStatement).filter(BillingStatement.id == stmt_id).first()
    if not stmt:
        db.close()
        raise HTTPException(status_code=404, detail="Billing statement not found")

    new_billing_month = data.billing_month if data.billing_month is not None else stmt.billing_month
    new_billing_year = data.billing_year if data.billing_year is not None else stmt.billing_year
    if (new_billing_month, new_billing_year) != (stmt.billing_month, stmt.billing_year):
        clash = db.query(BillingStatement).filter(
            BillingStatement.id != stmt_id,
            BillingStatement.billing_month == new_billing_month,
            BillingStatement.billing_year == new_billing_year,
        ).first()
        if clash:
            db.close()
            raise HTTPException(
                status_code=409,
                detail=f"A statement for {new_billing_month}/{new_billing_year} already exists (id={clash.id}).",
            )

    new_period_end_month = data.period_end_month if data.period_end_month is not None else stmt.period_end_month
    new_period_end_year = data.period_end_year if data.period_end_year is not None else stmt.period_end_year

    if data.total_units_consumed is not None:
        stmt.total_units_consumed = data.total_units_consumed
    if data.total_cost is not None:
        stmt.total_cost = data.total_cost
    stmt.billing_month = new_billing_month
    stmt.billing_year = new_billing_year
    stmt.period_end_month = new_period_end_month
    stmt.period_end_year = new_period_end_year
    stmt.cost_per_unit = (
        round(stmt.total_cost / stmt.total_units_consumed, 4)
        if stmt.total_units_consumed and stmt.total_cost is not None
        else None
    )

    # A stub created by the failed-import fallback (see _create_stub_statement) is
    # "complete" once it has the same minimum field a successful import requires —
    # billing_month/billing_year — at which point it behaves like any other statement.
    if stmt.needs_review and stmt.billing_month is not None and stmt.billing_year is not None:
        stmt.needs_review = False

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
        "needs_review": stmt.needs_review,
    }


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


@app.get("/billing-verify")
async def billing_verify():
    """Compare each billing statement's AI-extracted consumption against summed household meter readings.

    Returns:
        One entry per billing statement with a known period (needs-review stubs excluded),
        each including the statement's reported vs. household-summed units, the discrepancy,
        estimated money lost, and whether enough reading data existed to compute a comparison.
    """
    db = SessionLocal()
    # Excludes needs-review stubs (see _create_stub_statement) — without a known billing
    # period there's nothing to verify against the household meter sums, and the date
    # arithmetic below requires non-null billing_month/billing_year.
    stmts = db.query(BillingStatement).filter(
        BillingStatement.billing_month.isnot(None),
        BillingStatement.billing_year.isnot(None),
    ).order_by(
        BillingStatement.billing_year,
        BillingStatement.billing_month,
    ).all()
    all_readings = db.query(Reading).order_by(Reading.record_date).all()
    db.close()

    # Group readings by household (exclude the main/master meter, if present, to avoid double-counting)
    readings_by_mi: dict[str, list] = defaultdict(list)
    for r in all_readings:
        if r.mi == "MAIN":
            continue
        readings_by_mi[r.mi].append((r.record_date, r.reading, r.unit))

    results = []
    for stmt in stmts:
        end_month = stmt.period_end_month or stmt.billing_month
        end_year = stmt.period_end_year or stmt.billing_year

        household_sum_units = _household_sum_units(
            readings_by_mi, stmt.billing_month, stmt.billing_year, stmt.period_end_month, stmt.period_end_year
        )
        discrepancy_units = (
            round(stmt.total_units_consumed - household_sum_units, 3)
            if household_sum_units is not None and stmt.total_units_consumed is not None
            else None
        )
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
            "has_sufficient_readings": household_sum_units is not None,
        })

    return results


# Detect anomalies in usage via leak_rules.detect_historical_deviation's
# day-normalized, rolling-90-day-baseline methodology (SFPUC rule 4), which
# isn't skewed by differing period lengths and isn't thrown off by a single
# unusual prior period.
#
# The SFPUC doc's own trigger multiplier (leak_rules.RULE4_TRIGGER_MULTIPLIER,
# 1.5x / 50% increase) is too loose for individual households -- it flags far
# more households than this stricter 2.5x (150%) threshold does.
ANOMALY_TRIGGER_MULTIPLIER = 2.5


@app.get("/anomalies")
async def detect_anomalies():
    db = SessionLocal()
    rows = db.query(Reading).all()
    db.close()

    data = defaultdict(list)
    for r in rows:
        data[r.mi].append((r.record_date, _to_units(r.reading, r.unit)))

    anomalies = []
    for household, values in data.items():
        values.sort(key=lambda x: x[0])
        for alert in leak_rules.detect_historical_deviation(values, trigger_multiplier=ANOMALY_TRIGGER_MULTIPLIER):
            anomalies.append({"mi": household, **alert})

    return anomalies
