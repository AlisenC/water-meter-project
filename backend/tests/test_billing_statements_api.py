def test_billing_statements_empty(client):
    resp = client.get("/billing-statements")
    assert resp.status_code == 200
    assert resp.json() == []
