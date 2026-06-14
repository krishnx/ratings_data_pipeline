"""
OpenAPI completeness gate — all endpoints must be documented.
"""

EXPECTED_ENDPOINTS = {
    ("get", "/companies"),
    ("get", "/companies/{company_id}"),
    ("get", "/companies/{company_id}/versions"),
    ("get", "/companies/{company_id}/history"),
    ("get", "/companies/compare"),
    ("get", "/snapshots"),
    ("get", "/snapshots/latest"),
    ("get", "/snapshots/{snapshot_id}"),
    ("get", "/uploads"),
    ("get", "/uploads/{upload_id}/details"),
    ("get", "/uploads/{upload_id}/file"),
    ("get", "/uploads/stats"),
    ("get", "/health"),
}


def test_openapi_all_endpoints_present(client):
    schema = client.get("/openapi.json").json()
    found = {
        (method, path) for path, methods in schema["paths"].items() for method in methods if method != "parameters"
    }
    missing = EXPECTED_ENDPOINTS - found
    assert not missing, f"Missing from OpenAPI schema: {missing}"


def test_openapi_all_endpoints_have_summary(client):
    schema = client.get("/openapi.json").json()
    without_summary = [
        f"{method.upper()} {path}"
        for path, methods in schema["paths"].items()
        for method, detail in methods.items()
        if method != "parameters" and not detail.get("summary")
    ]
    assert not without_summary, f"Endpoints missing summary: {without_summary}"


def test_swagger_ui_accessible(client):
    r = client.get("/docs")
    assert r.status_code == 200


def test_redoc_accessible(client):
    r = client.get("/redoc")
    assert r.status_code == 200
