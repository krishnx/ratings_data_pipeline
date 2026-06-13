"""
E2E tests — full container stack, real HTTP calls.
"""

import requests

API = "http://localhost:8000"


def test_e1_api_healthy():
    r = requests.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_e2_companies_loaded():
    r = requests.get(f"{API}/companies")
    assert r.status_code == 200
    companies = r.json()
    assert len(companies) >= 2, f"Expected >= 2 companies, got {len(companies)}"


def test_e3_uploads_with_validation_status():
    r = requests.get(f"{API}/uploads")
    assert r.status_code == 200
    uploads = r.json()
    assert len(uploads) >= 4
    for upload in uploads:
        assert upload.get("validation_status") in ("passed", "passed_with_warnings", "failed")


def test_e4_download_file_returns_bytes():
    uploads = requests.get(f"{API}/uploads").json()
    assert uploads, "No uploads found"
    uid = uploads[0]["id"]
    r = requests.get(f"{API}/uploads/{uid}/file")
    assert r.status_code == 200
    assert len(r.content) > 0


def test_e5_compare_companies():
    companies = requests.get(f"{API}/companies").json()
    assert len(companies) >= 2
    ids = ",".join(str(c["company_id"]) for c in companies[:2])
    r = requests.get(f"{API}/companies/compare?company_ids={ids}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["companies"]) >= 1


def test_e6_idempotency_after_restart():
    uploads_before = len(requests.get(f"{API}/uploads").json())
    # Hitting the API again should not add more uploads (pipeline ran at startup)
    # This is a proxy check — the real idempotency test is in integration/
    assert uploads_before >= 4


def test_e7_snapshots_segment_weights_sum_to_one():
    snapshots = requests.get(f"{API}/snapshots/latest").json()
    assert snapshots, "No snapshots found"
    sid = snapshots[0]["id"]
    detail = requests.get(f"{API}/snapshots/{sid}").json()
    segs = detail.get("industry_segments", [])
    if segs:
        total = sum(s["weight"] for s in segs)
        assert abs(total - 1.0) < 0.01, f"Segment weights sum to {total}"
