def test_active_session_auto_created(client):
    resp = client.get("/leak/sessions/active")
    assert resp.status_code == 200
    session = resp.json()
    assert session["status"] == "active"
    assert session["submeter_row_count"] == 0
    assert session["main_meter_row_count"] == 0


def test_active_session_is_stable_across_calls(client):
    first = client.get("/leak/sessions/active").json()
    second = client.get("/leak/sessions/active").json()
    assert first["id"] == second["id"]


def test_list_sessions_includes_active(client):
    active = client.get("/leak/sessions/active").json()
    resp = client.get("/leak/sessions")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert active["id"] in ids
