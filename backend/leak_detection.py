from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile

from . import csv_parser
from .database import SessionLocal
from .main_meter_csv import parse_main_meter_csv_bytes
from .models import LeakMainMeterReading, LeakSession, LeakSubmeterReading
from .units import to_units

router = APIRouter()

# Purely for float noise around zero — not a business tolerance like billing's
# DISCREPANCY_TOLERANCE_UNITS. Any real excess flags as a potential leak.
LEAK_EPSILON = 1e-6


def _get_or_create_active_session(db) -> LeakSession:
    session = db.query(LeakSession).filter(LeakSession.status == "active").first()
    if session is None:
        session = LeakSession(status="active", created_at=datetime.utcnow())
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def _session_summary(db, session: LeakSession) -> dict:
    submeter_rows = db.query(LeakSubmeterReading).filter(LeakSubmeterReading.session_id == session.id).all()
    main_rows = db.query(LeakMainMeterReading).filter(LeakMainMeterReading.session_id == session.id).all()
    dates = [r.record_date for r in submeter_rows] + [r.read_time for r in main_rows]
    return {
        "id": session.id,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "archived_at": session.archived_at.isoformat() if session.archived_at else None,
        "submeter_row_count": len(submeter_rows),
        "main_meter_row_count": len(main_rows),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
    }


@router.get("/sessions")
async def list_sessions():
    db = SessionLocal()
    sessions = db.query(LeakSession).order_by(LeakSession.created_at.desc()).all()
    result = [_session_summary(db, s) for s in sessions]
    db.close()
    return result


@router.get("/sessions/active")
async def get_active_session():
    db = SessionLocal()
    session = _get_or_create_active_session(db)
    result = _session_summary(db, session)
    db.close()
    return result


@router.post("/submeter/import/preview")
async def submeter_import_preview(file: UploadFile = File(...)):
    file_bytes = await file.read()
    try:
        _, valid_rows, error_rows = csv_parser.parse_csv_bytes(file_bytes, file.filename, {}, fmt_override="A")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    dates = [r["record_date"] for r in valid_rows]
    return {
        "filename": file.filename,
        "valid_rows": len(valid_rows),
        "error_rows": len(error_rows),
        "households": sorted({r["mi"] for r in valid_rows}),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
        "errors": error_rows,
    }


@router.post("/submeter/import/confirm")
async def submeter_import_confirm(file: UploadFile = File(...)):
    file_bytes = await file.read()
    try:
        _, valid_rows, error_rows = csv_parser.parse_csv_bytes(file_bytes, file.filename, {}, fmt_override="A")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db = SessionLocal()
    session = _get_or_create_active_session(db)
    for row in valid_rows:
        db.add(LeakSubmeterReading(
            session_id=session.id,
            mi=row["mi"],
            reading=row["reading"],
            record_date=datetime.combine(row["record_date"], datetime.min.time()),
            unit=row["unit"],
        ))
    db.commit()
    db.close()
    return {"inserted": len(valid_rows), "skipped": len(error_rows), "errors": error_rows}


@router.post("/main-meter/import/preview")
async def main_meter_import_preview(file: UploadFile = File(...)):
    file_bytes = await file.read()
    try:
        valid_rows, error_rows = parse_main_meter_csv_bytes(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    dates = [r["read_time"] for r in valid_rows]
    return {
        "filename": file.filename,
        "valid_rows": len(valid_rows),
        "error_rows": len(error_rows),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
        "errors": error_rows,
    }


@router.post("/main-meter/import/confirm")
async def main_meter_import_confirm(file: UploadFile = File(...)):
    file_bytes = await file.read()
    try:
        valid_rows, error_rows = parse_main_meter_csv_bytes(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db = SessionLocal()
    session = _get_or_create_active_session(db)
    for row in valid_rows:
        db.add(LeakMainMeterReading(
            session_id=session.id,
            account_id=row["account_id"],
            meter_id=row["meter_id"],
            meter_sn=row["meter_sn"],
            read_time=row["read_time"],
            read_value=row["read_value"],
            flow_time=row["flow_time"],
            flow_value=row["flow_value"],
            register=row["register"],
        ))
    db.commit()
    db.close()
    return {"inserted": len(valid_rows), "skipped": len(error_rows), "errors": error_rows}


@router.get("/sessions/{session_id}/analysis")
async def session_analysis(session_id: int):
    db = SessionLocal()
    session = db.query(LeakSession).filter(LeakSession.id == session_id).first()
    if not session:
        db.close()
        raise HTTPException(status_code=404, detail="Leak session not found")

    main_rows = (
        db.query(LeakMainMeterReading)
        .filter(LeakMainMeterReading.session_id == session_id, LeakMainMeterReading.flow_time.isnot(None))
        .order_by(LeakMainMeterReading.flow_time)
        .all()
    )
    submeter_rows = (
        db.query(LeakSubmeterReading)
        .filter(LeakSubmeterReading.session_id == session_id)
        .order_by(LeakSubmeterReading.record_date)
        .all()
    )
    db.close()

    by_mi = defaultdict(list)
    for r in submeter_rows:
        by_mi[r.mi].append(r)

    # Mirrors backend/main.py's _household_sum_units bracket pattern, but per-day and
    # session-scoped. The first main-meter row only supplies a baseline boundary — like
    # the existing monthly comparison charts, a period needs a *previous* reading to diff against.
    periods = []
    for i in range(1, len(main_rows)):
        prev_row = main_rows[i - 1]
        curr_row = main_rows[i]
        period_start = prev_row.flow_time
        period_end = curr_row.flow_time

        submeter_sum = 0.0
        has_submeter_data = False
        for rows in by_mi.values():
            before_start = [r for r in rows if r.record_date <= period_start]
            before_end = [r for r in rows if r.record_date <= period_end]
            if not before_start or not before_end:
                continue
            baseline = before_start[-1]
            end_rdg = before_end[-1]
            if baseline.id == end_rdg.id:
                continue
            submeter_sum += max(0.0, to_units(end_rdg.reading, end_rdg.unit) - to_units(baseline.reading, baseline.unit))
            has_submeter_data = True

        main_flow = curr_row.flow_value
        submeter_sum = round(submeter_sum, 3) if has_submeter_data else None
        difference = (
            round(submeter_sum - main_flow, 3)
            if submeter_sum is not None and main_flow is not None
            else None
        )

        periods.append({
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "main_flow": main_flow,
            "submeter_sum": submeter_sum,
            "difference": difference,
            "has_submeter_data": has_submeter_data,
            "is_leak": difference is not None and difference > LEAK_EPSILON,
        })

    return periods


@router.post("/sessions/{session_id}/archive")
async def archive_session(session_id: int):
    db = SessionLocal()
    session = db.query(LeakSession).filter(LeakSession.id == session_id).first()
    if not session:
        db.close()
        raise HTTPException(status_code=404, detail="Leak session not found")
    if session.status != "active":
        db.close()
        raise HTTPException(status_code=400, detail="Session is not currently active")

    session.status = "archived"
    session.archived_at = datetime.utcnow()
    db.commit()
    result = _session_summary(db, session)
    db.close()
    return result


@router.post("/sessions/{session_id}/restore")
async def restore_session(session_id: int):
    db = SessionLocal()
    session = db.query(LeakSession).filter(LeakSession.id == session_id).first()
    if not session:
        db.close()
        raise HTTPException(status_code=404, detail="Leak session not found")
    if session.status != "archived":
        db.close()
        raise HTTPException(status_code=400, detail="Session is not currently archived")

    current_active = db.query(LeakSession).filter(LeakSession.status == "active").first()
    if current_active:
        current_active.status = "archived"
        current_active.archived_at = datetime.utcnow()

    session.status = "active"
    session.archived_at = None
    db.commit()
    result = _session_summary(db, session)
    db.close()
    return result
