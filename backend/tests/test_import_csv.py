import pytest
from sqlalchemy.exc import IntegrityError


def _csv_file(filename: str, rows: list[tuple[str, float, str, int]]):
    lines = ["mi,reading,record_date,unit"]
    for mi, reading, record_date, unit in rows:
        lines.append(f"{mi},{reading},{record_date},{unit}")
    body = ("\n".join(lines) + "\n").encode()
    return ("files", (filename, body, "text/csv"))


def test_confirm_exact_duplicate_skipped_across_two_imports(client):
    csv1 = _csv_file("a.csv", [("H1", 100.0, "2024-01-01", 1)])
    resp = client.post("/import-csv/confirm", files=[csv1])
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1

    csv2 = _csv_file("a.csv", [("H1", 100.0, "2024-01-01", 1)])
    resp = client.post("/import-csv/confirm", files=[csv2])
    body = resp.json()
    assert body["inserted"] == 0
    assert body["duplicates"] == 1
    assert body["conflicts"] == 0

    readings = client.get("/readings").json()
    assert len(readings) == 1


def test_confirm_conflict_flagged_and_not_overwritten(client):
    csv1 = _csv_file("a.csv", [("H1", 100.0, "2024-01-01", 1)])
    client.post("/import-csv/confirm", files=[csv1])
    original_id = client.get("/readings").json()[0]["id"]

    csv2 = _csv_file("a.csv", [("H1", 105.0, "2024-01-01", 1)])
    resp = client.post("/import-csv/confirm", files=[csv2])
    body = resp.json()
    assert body["inserted"] == 0
    assert body["conflicts"] == 1
    assert body["duplicates"] == 0
    conflict = body["conflict_rows"][0]
    assert conflict["mi"] == "H1"
    assert conflict["existing_reading"] == 100.0
    assert conflict["new_reading"] == 105.0
    assert conflict["existing_id"] == original_id

    readings = client.get("/readings").json()
    assert len(readings) == 1
    assert readings[0]["reading"] == 100.0


def test_confirm_in_batch_duplicate_across_two_files(client):
    csv_a = _csv_file("a.csv", [("H1", 100.0, "2024-01-01", 1)])
    csv_b = _csv_file("b.csv", [("H1", 100.0, "2024-01-01", 1)])

    resp = client.post("/import-csv/confirm", files=[csv_a, csv_b])
    body = resp.json()
    assert body["inserted"] == 1
    assert body["duplicates"] == 1
    per_file = {pf["filename"]: pf for pf in body["per_file"]}
    assert per_file["a.csv"]["inserted"] == 1
    assert per_file["b.csv"]["duplicates"] == 1

    readings = client.get("/readings").json()
    assert len(readings) == 1


def test_confirm_in_batch_conflict_across_two_files(client):
    csv_a = _csv_file("a.csv", [("H1", 100.0, "2024-01-01", 1)])
    csv_b = _csv_file("b.csv", [("H1", 999.0, "2024-01-01", 1)])

    resp = client.post("/import-csv/confirm", files=[csv_a, csv_b])
    body = resp.json()
    assert body["inserted"] == 1
    assert body["conflicts"] == 1
    conflict = body["conflict_rows"][0]
    assert conflict["existing_id"] is None  # H1's row from a.csv wasn't in the DB before this call

    readings = client.get("/readings").json()
    assert len(readings) == 1
    assert readings[0]["reading"] == 100.0


def test_preview_reports_duplicates_and_conflicts_without_writing(client):
    seed = _csv_file("seed.csv", [("H1", 100.0, "2024-01-01", 1)])
    client.post("/import-csv/confirm", files=[seed])

    preview_csv = _csv_file("a.csv", [
        ("H1", 100.0, "2024-01-01", 1),  # duplicate
        ("H1", 999.0, "2024-01-02", 1),  # new row, not a conflict
    ])
    resp = client.post("/import-csv/preview", files=[preview_csv])
    body = resp.json()
    assert body["total_duplicates"] == 1
    assert body["total_conflicts"] == 0
    fp = body["files"][0]
    assert fp["duplicate_rows"] == 1
    assert fp["rows_after_filter"] == 1

    readings = client.get("/readings").json()
    assert len(readings) == 1  # preview never writes


def test_readings_unique_constraint_enforced():
    from backend.database import SessionLocal
    from backend.models import Reading
    from datetime import datetime

    db = SessionLocal()
    try:
        db.add(Reading(mi="H1", reading=100.0, record_date=datetime(2024, 1, 1), unit=1))
        db.commit()

        db.add(Reading(mi="H1", reading=200.0, record_date=datetime(2024, 1, 1), unit=1))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_resolve_single_conflict(client):
    seed = _csv_file("seed.csv", [("H1", 100.0, "2024-01-01", 1)])
    client.post("/import-csv/confirm", files=[seed])
    existing_id = client.get("/readings").json()[0]["id"]

    resp = client.post("/readings/resolve-conflicts", json={
        "resolutions": [{"id": existing_id, "reading": 105.0, "unit": 1}]
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == 1
    assert body["not_found"] == []

    readings = client.get("/readings").json()
    assert len(readings) == 1
    assert readings[0]["id"] == existing_id
    assert readings[0]["reading"] == 105.0


def test_resolve_multiple_conflicts(client):
    seed = _csv_file("seed.csv", [("H1", 100.0, "2024-01-01", 1), ("H2", 50.0, "2024-01-01", 1)])
    client.post("/import-csv/confirm", files=[seed])
    readings = {r["mi"]: r["id"] for r in client.get("/readings").json()}

    resp = client.post("/readings/resolve-conflicts", json={
        "resolutions": [
            {"id": readings["H1"], "reading": 111.0, "unit": 1},
            {"id": readings["H2"], "reading": 222.0, "unit": 1},
        ]
    })
    body = resp.json()
    assert body["updated"] == 2

    updated = {r["mi"]: r["reading"] for r in client.get("/readings").json()}
    assert updated == {"H1": 111.0, "H2": 222.0}


def test_resolve_not_found_reports_without_failing_batch(client):
    seed = _csv_file("seed.csv", [("H1", 100.0, "2024-01-01", 1)])
    client.post("/import-csv/confirm", files=[seed])
    existing_id = client.get("/readings").json()[0]["id"]
    missing_id = existing_id + 9999

    resp = client.post("/readings/resolve-conflicts", json={
        "resolutions": [
            {"id": existing_id, "reading": 150.0, "unit": 1},
            {"id": missing_id, "reading": 1.0, "unit": 1},
        ]
    })
    body = resp.json()
    assert body["updated"] == 1
    assert body["not_found"] == [missing_id]

    readings = client.get("/readings").json()
    assert readings[0]["reading"] == 150.0


def test_preview_confirm_resolve_integration(client):
    seed = _csv_file("seed.csv", [("H1", 100.0, "2024-01-01", 1), ("H2", 50.0, "2024-01-01", 1)])
    client.post("/import-csv/confirm", files=[seed])

    update_csv = _csv_file("update.csv", [
        ("H1", 150.0, "2024-01-01", 1),  # conflict, will be accepted
        ("H2", 999.0, "2024-01-01", 1),  # conflict, will be left alone
    ])
    preview = client.post("/import-csv/preview", files=[update_csv]).json()
    assert preview["total_conflicts"] == 2

    confirm = client.post("/import-csv/confirm", files=[update_csv]).json()
    assert confirm["conflicts"] == 2
    conflicts_by_mi = {c["mi"]: c for c in confirm["conflict_rows"]}

    resp = client.post("/readings/resolve-conflicts", json={
        "resolutions": [{
            "id": conflicts_by_mi["H1"]["existing_id"],
            "reading": conflicts_by_mi["H1"]["new_reading"],
            "unit": conflicts_by_mi["H1"]["new_unit"],
        }]
    })
    assert resp.json()["updated"] == 1

    final = {r["mi"]: r["reading"] for r in client.get("/readings").json()}
    assert final == {"H1": 150.0, "H2": 50.0}
