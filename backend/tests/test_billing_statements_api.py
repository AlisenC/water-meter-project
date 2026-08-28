def test_billing_statements_empty(client):
    resp = client.get("/billing-statements")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_blank_billing_statement(client):
    resp = client.post("/billing-statements")
    assert resp.status_code == 200
    body = resp.json()
    assert body["needs_review"] is True
    assert body["billing_month"] is None
    assert body["billing_year"] is None

    listed = client.get("/billing-statements").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]
    assert listed[0]["needs_review"] is True
