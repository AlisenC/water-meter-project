from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from . import csv_parser, leak_rules
from .database import SessionLocal
from .main_meter_csv import parse_main_meter_csv_bytes
from .models import LeakMainMeterReading, LeakSession, LeakSubmeterReading
from .units import to_units

router = APIRouter()

# SQLite has a hard cap on bound parameters per statement (historically 999);
# batching keeps a single bulk delete under that regardless of how many ids
# are selected, while still running as one request/transaction instead of one
# HTTP request per row (which is what was overwhelming SQLite's single-writer
# lock on large selections).
DELETE_CHUNK_SIZE = 500


class BulkDeleteRequest(BaseModel):
    ids: list[int]


def _bulk_delete(db, model, ids: list[int]) -> int:
    deleted = 0
    for i in range(0, len(ids), DELETE_CHUNK_SIZE):
        chunk = ids[i:i + DELETE_CHUNK_SIZE]
        deleted += db.query(model).filter(model.id.in_(chunk)).delete(synchronize_session=False)
    return deleted

# Purely for float noise around zero — not a business tolerance like billing's
# DISCREPANCY_TOLERANCE_UNITS. Any real excess flags as a potential leak.
LEAK_EPSILON = 1e-6

# How far (in either direction) a main-meter reading may sit from a submeter-driven
# period boundary and still be treated as "the closest" reading for that boundary.
# Guards against nearest-neighbor matching across a gap in main-meter coverage
# (e.g. main data only exists for January but the submeter period is in August).
MAIN_MATCH_TOLERANCE = timedelta(hours=36)


# Spacing of points on the main meter flow line chart — one point per day.
FLOW_CHART_INTERVAL = timedelta(days=1)


def _flow_chart_window(submeter_rows):
    """[start, end] window the main-meter flow chart should cover: from one day
    before the earliest submeter reading date through the end of the latest
    submeter reading date. Returns None if there are no submeter readings —
    the chart has no meaningful range to draw without them.
    """
    if not submeter_rows:
        return None
    submeter_days = [r.record_date.date() for r in submeter_rows]
    start = datetime.combine(min(submeter_days) - timedelta(days=1), datetime.min.time())
    end = datetime.combine(max(submeter_days) + timedelta(days=1), datetime.min.time())
    return start, end


def _flow_chart_grid(start: datetime, end: datetime):
    grid = []
    t = start
    while t <= end:
        grid.append(t)
        t += FLOW_CHART_INTERVAL
    return grid


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


def _split_duplicates(rows, existing_keys, key_fn, filename):
    """Splits `rows` into (kept, duplicates) against `existing_keys` (e.g. keys
    already present in the session's DB rows). Repeats within `rows` itself
    are also treated as duplicates of the first occurrence, so re-uploading
    the same file — or a file with internal repeats — is caught too.
    """
    seen = set(existing_keys)
    kept, duplicates = [], []
    for row in rows:
        key = key_fn(row)
        if key in seen:
            label = " / ".join(str(part) for part in key) if isinstance(key, tuple) else str(key)
            duplicates.append({
                "row_num": row.get("row_num"),
                "reason": "duplicate_entry",
                "raw_value": label,
                "filename": filename,
            })
            continue
        seen.add(key)
        kept.append(row)
    return kept, duplicates


def _get_or_create_active_session(db) -> LeakSession:
    session = db.query(LeakSession).filter(LeakSession.status == "active").first()
    if session is None:
        session = LeakSession(status="active", created_at=datetime.utcnow())
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def _active_session_readonly(db) -> LeakSession | None:
    """Like _get_or_create_active_session, but never creates one — for preview
    endpoints, which must stay side-effect-free. No active session means no
    existing rows to dedupe against, so callers can treat that as "nothing to
    compare".
    """
    return db.query(LeakSession).filter(LeakSession.status == "active").first()


def _existing_submeter_keys(db, session_id):
    return {
        (mi, record_date)
        for mi, record_date in db.query(LeakSubmeterReading.mi, LeakSubmeterReading.record_date)
        .filter(LeakSubmeterReading.session_id == session_id)
        .all()
    }


def _existing_main_meter_keys(db, session_id):
    return {
        read_time
        for (read_time,) in db.query(LeakMainMeterReading.read_time)
        .filter(LeakMainMeterReading.session_id == session_id)
        .all()
    }


def _property_mode(household_count: int) -> str:
    """"standard" (48h) or "multi_family" (72h) volume-threshold window, per the
    submeter household count. Assumes complete submeter coverage -- every
    household on the property has been imported, so distinct `mi` count is an
    accurate stand-in for unit count. A main-meter-only session (no submeter
    data at all) derives to 0 and is treated as "standard".
    """
    if household_count >= leak_rules.MULTI_FAMILY_UNIT_THRESHOLD:
        return "multi_family"
    return "standard"


def _session_summary(db, session: LeakSession) -> dict:
    submeter_rows = db.query(LeakSubmeterReading).filter(LeakSubmeterReading.session_id == session.id).all()
    main_rows = db.query(LeakMainMeterReading).filter(LeakMainMeterReading.session_id == session.id).all()
    dates = [r.record_date for r in submeter_rows] + [r.read_time for r in main_rows]
    household_count = len({r.mi for r in submeter_rows})
    return {
        "id": session.id,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "archived_at": session.archived_at.isoformat() if session.archived_at else None,
        "submeter_row_count": len(submeter_rows),
        "main_meter_row_count": len(main_rows),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
        "household_count": household_count,
        "property_mode": _property_mode(household_count),
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


def _parse_submeter_csv(file_bytes: bytes, filename: str):
    """Adapts csv_parser.parse_csv_bytes's 3-tuple to the (valid_rows, error_rows) shape
    parse_main_meter_csv_bytes already returns, so both can share _leak_import_preview/confirm.
    """
    _, valid_rows, error_rows = csv_parser.parse_csv_bytes(
        file_bytes, filename, {}, fmt_override="A", parse_datetime=True
    )
    return valid_rows, error_rows


def _leak_import_preview(file_bytes: bytes, filename: str, parse_fn, existing_keys_fn, dedup_key_fn, date_field: str):
    """Shared preview step for the daily leak-detection CSV imports (submeter, main meter).

    Args:
        file_bytes: Raw uploaded file content.
        filename: Uploaded file's name, used in error rows and duplicate messages.
        parse_fn: (file_bytes, filename) -> (valid_rows, error_rows).
        existing_keys_fn: (db, session_id) -> set of existing dedup keys for the active session.
        dedup_key_fn: row -> hashable key used to detect duplicates against existing_keys_fn's result.
        date_field: Row dict key holding each row's date/datetime, used for date_min/date_max.

    Returns:
        (valid_rows, preview) where preview is the common preview response dict (filename,
        valid_rows, error_rows, date_min, date_max, errors); callers may add format-specific
        fields (e.g. "households") before returning it.
    """
    try:
        valid_rows, error_rows = parse_fn(file_bytes, filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db = SessionLocal()
    active = _active_session_readonly(db)
    existing_keys = existing_keys_fn(db, active.id) if active else set()
    db.close()

    valid_rows, duplicate_rows = _split_duplicates(valid_rows, existing_keys, dedup_key_fn, filename)
    error_rows = error_rows + duplicate_rows

    dates = [r[date_field] for r in valid_rows]
    preview = {
        "filename": filename,
        "valid_rows": len(valid_rows),
        "error_rows": len(error_rows),
        "date_min": min(dates).isoformat() if dates else None,
        "date_max": max(dates).isoformat() if dates else None,
        "errors": error_rows,
    }
    return valid_rows, preview


def _leak_import_confirm(file_bytes: bytes, filename: str, parse_fn, existing_keys_fn, dedup_key_fn, build_model_fn):
    """Shared confirm step for the daily leak-detection CSV imports (submeter, main meter).

    Args:
        file_bytes: Raw uploaded file content.
        filename: Uploaded file's name, used in error rows and duplicate messages.
        parse_fn: (file_bytes, filename) -> (valid_rows, error_rows).
        existing_keys_fn: (db, session_id) -> set of existing dedup keys for the session.
        dedup_key_fn: row -> hashable key used to detect duplicates against existing_keys_fn's result.
        build_model_fn: (session_id, row) -> ORM model instance to insert.

    Returns:
        {"inserted": int, "skipped": int, "errors": list} summarizing the import.
    """
    try:
        valid_rows, error_rows = parse_fn(file_bytes, filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db = SessionLocal()
    session = _get_or_create_active_session(db)

    existing_keys = existing_keys_fn(db, session.id)
    valid_rows, duplicate_rows = _split_duplicates(valid_rows, existing_keys, dedup_key_fn, filename)
    error_rows = error_rows + duplicate_rows

    for row in valid_rows:
        db.add(build_model_fn(session.id, row))
    db.commit()
    db.close()
    return {"inserted": len(valid_rows), "skipped": len(error_rows), "errors": error_rows}


@router.post("/submeter/import/preview")
async def submeter_import_preview(file: UploadFile = File(...)):
    file_bytes = await file.read()
    valid_rows, preview = _leak_import_preview(
        file_bytes, file.filename, _parse_submeter_csv, _existing_submeter_keys,
        lambda row: (row["mi"], row["record_date"]), "record_date",
    )
    preview["households"] = sorted({r["mi"] for r in valid_rows})
    return preview


@router.post("/submeter/import/confirm")
async def submeter_import_confirm(file: UploadFile = File(...)):
    file_bytes = await file.read()
    return _leak_import_confirm(
        file_bytes, file.filename, _parse_submeter_csv, _existing_submeter_keys,
        lambda row: (row["mi"], row["record_date"]),
        lambda session_id, row: LeakSubmeterReading(
            session_id=session_id,
            mi=row["mi"],
            reading=row["reading"],
            record_date=row["record_date"],
            unit=row["unit"],
        ),
    )


@router.post("/main-meter/import/preview")
async def main_meter_import_preview(file: UploadFile = File(...)):
    file_bytes = await file.read()
    _, preview = _leak_import_preview(
        file_bytes, file.filename, parse_main_meter_csv_bytes, _existing_main_meter_keys,
        lambda row: row["read_time"], "read_time",
    )
    return preview


@router.post("/main-meter/import/confirm")
async def main_meter_import_confirm(file: UploadFile = File(...)):
    file_bytes = await file.read()
    return _leak_import_confirm(
        file_bytes, file.filename, parse_main_meter_csv_bytes, _existing_main_meter_keys,
        lambda row: row["read_time"],
        lambda session_id, row: LeakMainMeterReading(
            session_id=session_id,
            account_id=row["account_id"],
            meter_id=row["meter_id"],
            meter_sn=row["meter_sn"],
            read_time=row["read_time"],
            read_value=row["read_value"],
            flow_time=row["flow_time"],
            flow_value=row["flow_value"],
            register=row["register"],
        ),
    )


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

    # Main meter's own timeline, restricted to the submeter-reported date range
    # (plus one day of lead-in) and resampled onto one point per day — each
    # grid mark is resolved to the closest actual main-meter reading (whatever
    # the import granularity), and each point is the delta from the previous
    # grid mark's reading. Grid marks with no main-meter reading nearby (outside
    # MAIN_MATCH_TOLERANCE) are skipped rather than faked.
    main_flow_series = []
    window = _flow_chart_window(submeter_rows)
    if window is not None:
        grid = _flow_chart_grid(*window)
        grid_matches = [(t, _closest_main_row(main_rows, t)) for t in grid]
        for i in range(1, len(grid_matches)):
            t_prev, prev_row = grid_matches[i - 1]
            t_curr, curr_row = grid_matches[i]
            if prev_row is None or curr_row is None:
                continue
            main_flow_series.append({
                "period_start": t_prev.isoformat(),
                "period_end": t_curr.isoformat(),
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

    # SFPUC rules 1-3 (continuous flow, volume threshold, nighttime ratio), main
    # meter only -- submeter data is manually read and too sparse for these rules
    # to ever apply. Additive alongside the main-vs-submeter comparison above, not
    # a replacement of it.
    household_count = len({r.mi for r in submeter_rows})
    property_mode = _property_mode(household_count)
    multi_family = property_mode == "multi_family"

    main_readings = [(r.read_time, r.read_value) for r in main_rows]
    sfpuc_main_meter = leak_rules.evaluate_meter_rules(
        main_readings,
        scope="main",
        mi=None,
        rule2_duration=leak_rules.RULE2_MULTI_FAMILY_DURATION if multi_family else leak_rules.RULE2_STANDARD_DURATION,
        nighttime_multiplier=leak_rules.NIGHT_STANDARD_MULTIPLIER,
        break_keys=[(r.meter_sn, r.register) for r in main_rows],
    )

    return {
        "main_flow_series": main_flow_series,
        "periods": periods,
        "sfpuc": {
            "property_mode": property_mode,
            "household_count": household_count,
            "main_meter": sfpuc_main_meter,
        },
    }


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
        has_data = (
            db.query(LeakSubmeterReading).filter(LeakSubmeterReading.session_id == current_active.id).first() is not None
            or db.query(LeakMainMeterReading).filter(LeakMainMeterReading.session_id == current_active.id).first() is not None
        )
        if has_data:
            current_active.status = "archived"
            current_active.archived_at = datetime.utcnow()
        else:
            # Nothing was ever imported into this workspace — drop it rather than
            # leaving a permanent zero-row entry cluttering Archived Sessions.
            db.delete(current_active)

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


@router.delete("/submeter")
async def delete_submeter_readings(payload: BulkDeleteRequest):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    db = SessionLocal()
    deleted = _bulk_delete(db, LeakSubmeterReading, payload.ids)
    db.commit()
    db.close()
    return {"deleted": deleted}


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


@router.delete("/main-meter")
async def delete_main_meter_readings(payload: BulkDeleteRequest):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="No ids provided")
    db = SessionLocal()
    deleted = _bulk_delete(db, LeakMainMeterReading, payload.ids)
    db.commit()
    db.close()
    return {"deleted": deleted}
