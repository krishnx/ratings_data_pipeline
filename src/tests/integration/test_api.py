"""
Integration tests for all API endpoints against a real PostgreSQL test DB.
Requires TEST_DATABASE_URL to point at a seeded database.
Run: pytest tests/integration/ -v
"""
import pytest


@pytest.fixture(scope="module", autouse=True)
def seed_pipeline(db_session_factory):
    """Run the pipeline once for the module so all 4 files are loaded."""
    import os
    from pathlib import Path

    from api.pipeline.runner import run_pipeline

    data_dir = os.environ.get(
        "TEST_DATA_DIR",
        str(Path(__file__).parent.parent.parent.parent / "data_main" / "data"),
    )
    if Path(data_dir).exists():
        run_pipeline(data_dir, db_session_factory)


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Companies ─────────────────────────────────────────────────────────────────

def test_list_companies(client):
    r = client.get("/companies")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_company_by_id(client):
    companies = client.get("/companies").json()
    if not companies:
        pytest.skip("No companies in DB")
    cid = companies[0]["company_id"]
    r = client.get(f"/companies/{cid}")
    assert r.status_code == 200
    body = r.json()
    assert "entity_name" in body
    assert "industry_segments" in body
    assert "credit_metrics" in body


def test_get_company_versions(client):
    companies = client.get("/companies").json()
    if not companies:
        pytest.skip("No companies in DB")
    cid = companies[0]["company_id"]
    r = client.get(f"/companies/{cid}/versions")
    assert r.status_code == 200
    versions = r.json()
    assert isinstance(versions, list)
    assert len(versions) >= 1


def test_get_company_history(client):
    companies = client.get("/companies").json()
    if not companies:
        pytest.skip("No companies in DB")
    cid = companies[0]["company_id"]
    r = client.get(f"/companies/{cid}/history")
    assert r.status_code == 200
    history = r.json()
    assert isinstance(history, list)
    for entry in history:
        assert "credit_metrics" in entry


def test_compare_companies(client):
    companies = client.get("/companies").json()
    if len(companies) < 1:
        pytest.skip("Need at least 1 company")
    ids = ",".join(str(c["company_id"]) for c in companies[:2])
    r = client.get(f"/companies/compare?company_ids={ids}")
    assert r.status_code == 200
    body = r.json()
    assert "as_of_date" in body
    assert "companies" in body


def test_compare_empty_company_ids_returns_400(client):
    r = client.get("/companies/compare?company_ids=")
    assert r.status_code == 400


def test_get_nonexistent_company_returns_404(client):
    r = client.get("/companies/999999")
    assert r.status_code == 404


# ── Snapshots ─────────────────────────────────────────────────────────────────

def test_list_snapshots(client):
    r = client.get("/snapshots")
    assert r.status_code == 200
    body = r.json()
    assert "total_count" in body
    assert "items" in body


def test_list_snapshots_sector_filter(client):
    r = client.get("/snapshots")
    items = r.json().get("items", [])
    if not items:
        pytest.skip("No snapshots in DB")
    sector = items[0].get("corporate_sector")
    if not sector:
        pytest.skip("No sector available")
    r2 = client.get(f"/snapshots?sector={sector}")
    assert r2.status_code == 200
    for item in r2.json()["items"]:
        assert item["corporate_sector"] == sector


def test_list_snapshots_pagination(client):
    r = client.get("/snapshots?page_size=1&page=1")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) <= 1
    assert body["total_count"] >= 0


def test_snapshots_latest(client):
    r = client.get("/snapshots/latest")
    assert r.status_code == 200
    latest = r.json()
    assert isinstance(latest, list)


def test_get_snapshot_by_id(client):
    snapshots = client.get("/snapshots/latest").json()
    if not snapshots:
        pytest.skip("No snapshots in DB")
    sid = snapshots[0]["id"]
    r = client.get(f"/snapshots/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert "industry_segments" in body
    assert "credit_metrics" in body


def test_get_nonexistent_snapshot_returns_404(client):
    r = client.get("/snapshots/999999")
    assert r.status_code == 404


# ── Uploads ───────────────────────────────────────────────────────────────────

def test_list_uploads(client):
    r = client.get("/uploads")
    assert r.status_code == 200
    uploads = r.json()
    assert isinstance(uploads, list)


def test_get_upload_details(client):
    uploads = client.get("/uploads").json()
    if not uploads:
        pytest.skip("No uploads in DB")
    uid = uploads[0]["id"]
    r = client.get(f"/uploads/{uid}/details")
    assert r.status_code == 200
    body = r.json()
    assert "validation_report" in body


def test_download_upload_file(client):
    uploads = client.get("/uploads").json()
    if not uploads:
        pytest.skip("No uploads in DB")
    uid = uploads[0]["id"]
    r = client.get(f"/uploads/{uid}/file")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert len(r.content) > 0


def test_upload_stats(client):
    r = client.get("/uploads/stats")
    assert r.status_code == 200
    body = r.json()
    assert "files_processed" in body
    assert "by_sector" in body


def test_nonexistent_upload_returns_404(client):
    r = client.get("/uploads/999999/details")
    assert r.status_code == 404


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_pipeline_idempotency(db_session_factory):
    """Running pipeline twice must not create duplicate uploads."""
    import os
    from pathlib import Path

    from api.pipeline.runner import run_pipeline
    from api.models.orm import UploadAudit

    data_dir = os.environ.get(
        "TEST_DATA_DIR",
        str(Path(__file__).parent.parent.parent.parent / "data_main" / "data"),
    )
    if not Path(data_dir).exists():
        pytest.skip("Data files not available")

    session = db_session_factory()
    count_before = session.query(UploadAudit).count()
    session.close()

    result = run_pipeline(data_dir, db_session_factory)

    session = db_session_factory()
    count_after = session.query(UploadAudit).count()
    session.close()

    assert count_after == count_before  # no new rows
    assert result["files_processed"] == 0  # all skipped
    assert result["files_skipped"] == result["files_found"]
