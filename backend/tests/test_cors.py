def _preflight(client, origin):
    return client.options(
        "/api/v1/assets",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_vite_origin_allowed(client):
    r = _preflight(client, "http://localhost:5173")
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unlisted_origin_rejected(client):
    r = _preflight(client, "http://evil.example")
    assert "access-control-allow-origin" not in r.headers


def test_error_responses_carry_cors_headers(client):
    r = client.get("/api/v1/assets/nope", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 404
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
