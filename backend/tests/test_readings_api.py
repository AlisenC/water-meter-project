def test_add_get_delete_reading(client):
    resp = client.post("/readings", json={"mi": "TESTMETER", "reading": 12.5})
    assert resp.status_code == 200
    created = resp.json()
    assert created["mi"] == "TESTMETER"
    assert created["reading"] == 12.5
    reading_id = created["id"]

    resp = client.get("/readings")
    assert resp.status_code == 200
    readings = resp.json()
    assert len(readings) == 1
    assert readings[0]["id"] == reading_id

    resp = client.delete(f"/readings/{reading_id}")
    assert resp.status_code == 200

    resp = client.get("/readings")
    assert resp.json() == []


def test_get_readings_empty(client):
    resp = client.get("/readings")
    assert resp.status_code == 200
    assert resp.json() == []
