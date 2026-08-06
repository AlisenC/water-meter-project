from collections import defaultdict
from datetime import datetime, timedelta

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

# How far (in either direction) a main-meter reading may sit from a submeter-driven
# period boundary and still be treated as "the closest" reading for that boundary.
# Guards against nearest-neighbor matching across a gap in main-meter coverage
# (e.g. main data only exists for January but the submeter period is in August).
MAIN_MATCH_TOLERANCE = timedelta(hours=36)


def _closest_main_row(main_rows_sorted, target: datetime):
    """Nearest main-meter row to `target` by read_time, within MAIN_MATCH_TOLERANCE.
    main_rows_sorted must already be ordered by read_time. Returns None if there are
    no rows, or the nearest one is farther than the tolerance allows.
    """
    if not main_rows_sorted:
        return None
    best = min(main_rows_sorted, key=lambda r: abs(r.read_time - target))
    if abs(best.read_time - target) > MAIN_MATCH_TOLERANCE:
        return None
    return best


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
        .filter(LeakMainMeterReading.session_id == session_id)
        .order_by(LeakMainMeterReading.read_time)
        .all()
    )
    submeter_rows = (
        db.query(LeakSubmeterReading)
        .filter(LeakSubmeterReading.session_id == session_id)
        .order_by(LeakSubmeterReading.record_date)
        .all()
    )
    db.close()

    # Main meter's own timeline, at whatever granularity it was imported (daily,
    # hourly, 15-min, ...) — each point is the delta from the previous reading.
    main_flow_series = []
    for i in range(1, len(main_rows)):
        prev_row = main_rows[i - 1]
        curr_row = main_rows[i]
        main_flow_series.append({
            "period_start": prev_row.read_time.isoformat(),
            "period_end": curr_row.read_time.isoformat(),
            "flow": round(curr_row.read_value - prev_row.read_value, 3),
        })

    by_mi = defaultdict(list)
    for r in submeter_rows:
        by_mi[r.mi].append(r)

    # Periods are anchored to the submeters' own reporting cadence (sparse and
    # irregular) rather than the main meter's, since that's what actually varies
    # here. For each period, the main-meter side of the comparison is resolved by
    # finding the closest main-meter reading to each boundary — this is what lets
    # the main meter be imported at any granularity (daily, hourly, 15-min) without
    # requiring it to align with submeter timestamps.
    submeter_times = sorted({r.record_date for r in submeter_rows})

    periods = []
    for i in range(1, len(submeter_times)):
        t_prev = submeter_times[i - 1]
        t_curr = submeter_times[i]

        submeter_delta = 0.0
        has_submeter_data = False
        for rows in by_mi.values():
            before_start = [r for r in rows if r.record_date <= t_prev]
            before_end = [r for r in rows if r.record_date <= t_curr]
            if not before_start or not before_end:
                continue
            baseline = before_start[-1]
            end_rdg = before_end[-1]
            if baseline.id == end_rdg.id:
                continue
            submeter_delta += max(0.0, to_units(end_rdg.reading, end_rdg.unit) - to_units(baseline.reading, baseline.unit))
            has_submeter_data = True

        if not has_submeter_data:
            continue

        main_start_row = _closest_main_row(main_rows, t_prev)
        main_end_row = _closest_main_row(main_rows, t_curr)

        main_delta = None
        if main_start_row is not None and main_end_row is not None and main_start_row.id != main_end_row.id:
            main_delta = round(main_end_row.read_value - main_start_row.read_value, 3)

        submeter_delta = round(submeter_delta, 3)
        difference = round(main_delta - submeter_delta, 3) if main_delta is not None else None

        periods.append({
            "period_start": t_prev.isoformat(),
            "period_end": t_curr.isoformat(),
            "submeter_delta": submeter_delta,
            "main_delta": main_delta,
            "main_period_start_actual": main_start_row.read_time.isoformat() if main_start_row else None,
            "main_period_end_actual": main_end_row.read_time.isoformat() if main_end_row else None,
            "difference": difference,
            "is_leak": difference is not None and difference > LEAK_EPSILON,
        })

    return {"main_flow_series": main_flow_series, "periods": periods}


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


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int):
    db = SessionLocal()
    session = db.query(LeakSession).filter(LeakSession.id == session_id).first()
    if not session:
        db.close()
        raise HTTPException(status_code=404, detail="Leak session not found")
    if session.status == "active":
        db.close()
        raise HTTPException(status_code=400, detail="Cannot delete the active session — archive or restore another session first")

    db.query(LeakSubmeterReading).filter(LeakSubmeterReading.session_id == session_id).delete()
    db.query(LeakMainMeterReading).filter(LeakMainMeterReading.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    db.close()
    return {"ok": True}


@router.get("/sessions/{session_id}/submeter-readings")
async def list_submeter_readings(session_id: int):
    db = SessionLocal()
    session = db.query(LeakSession).filter(LeakSession.id == session_id).first()
    if not session:
        db.close()
        raise HTTPException(status_code=404, detail="Leak session not found")
    rows = (
        db.query(LeakSubmeterReading)
        .filter(LeakSubmeterReading.session_id == session_id)
        .order_by(LeakSubmeterReading.record_date)
        .all()
    )
    db.close()
    return [
        {"id": r.id, "mi": r.mi, "reading": r.reading, "record_date": r.record_date.isoformat(), "unit": r.unit}
        for r in rows
    ]


@router.get("/sessions/{session_id}/main-meter-readings")
async def list_main_meter_readings(session_id: int):
    db = SessionLocal()
    session = db.query(LeakSession).filter(LeakSession.id == session_id).first()
    if not session:
        db.close()
        raise HTTPException(status_code=404, detail="Leak session not found")
    rows = (
        db.query(LeakMainMeterReading)
        .filter(LeakMainMeterReading.session_id == session_id)
        .order_by(LeakMainMeterReading.read_time)
        .all()
    )
    db.close()
    return [
        {
            "id": r.id,
            "read_time": r.read_time.isoformat(),
            "read_value": r.read_value,
            "flow_time": r.flow_time.isoformat() if r.flow_time else None,
            "flow_value": r.flow_value,
        }
        for r in rows
    ]


@router.delete("/submeter/{reading_id}")
async def delete_submeter_reading(reading_id: int):
    db = SessionLocal()
    reading = db.query(LeakSubmeterReading).filter(LeakSubmeterReading.id == reading_id).first()
    if not reading:
        db.close()
        raise HTTPException(status_code=404, detail="Submeter reading not found")
    db.delete(reading)
    db.commit()
    db.close()
    return {"ok": True}


@router.delete("/main-meter/{reading_id}")
async def delete_main_meter_reading(reading_id: int):
    db = SessionLocal()
    reading = db.query(LeakMainMeterReading).filter(LeakMainMeterReading.id == reading_id).first()
    if not reading:
        db.close()
        raise HTTPException(status_code=404, detail="Main meter reading not found")
    db.delete(reading)
    db.commit()
    db.close()
    return {"ok": True}
