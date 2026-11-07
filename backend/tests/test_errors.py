from backend.app.schemas.errors import ErrorResponse


def _error(r):
    return ErrorResponse.model_validate(r.json()).error


def test_unknown_asset_returns_404_envelope(client):
    r = client.get("/api/v1/assets/cooling-99")
    assert r.status_code == 404
    err = _error(r)
    assert err.code == "ASSET_NOT_FOUND"
    assert err.details == {"asset_id": "cooling-99"}
    assert err.request_id == r.headers["X-Request-ID"]


def test_request_id_is_echoed(client):
    r = client.get("/api/v1/assets/cooling-99", headers={"X-Request-ID": "req-test-123"})
    assert _error(r).request_id == "req-test-123"
    assert r.headers["X-Request-ID"] == "req-test-123"


def test_query_validation_is_normalized_to_422_envelope(client):
    r = client.get("/api/v1/assets?limit=0")
    assert r.status_code == 422
    err = _error(r)
    assert err.code == "VALIDATION_ERROR"
    assert err.details["errors"][0]["loc"] == ["query", "limit"]
    assert "input" not in err.details["errors"][0]


def test_unknown_route_uses_envelope(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert _error(r).code == "NOT_FOUND"


def test_wrong_method_uses_envelope(client):
    r = client.delete("/api/v1/assets")
    assert r.status_code == 405
    assert _error(r).code == "METHOD_NOT_ALLOWED"
