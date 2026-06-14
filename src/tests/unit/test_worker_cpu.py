"""
Unit tests for the CPU pipeline worker.

cpu_worker() is called directly in-process — no ProcessPoolExecutor needed.
Error-path tests mock the extractor/validator to avoid filesystem I/O.
Happy-path tests use the real .xlsm files from data/.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from api.pipeline.exceptions import MissingSheetError
from api.pipeline.worker_cpu import CPUResult, cpu_worker

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
_XLSM = sorted(DATA_DIR.glob("*.xlsm"))


@pytest.fixture()
def real_file() -> Path:
    if not _XLSM:
        pytest.skip("No .xlsm files found in data/")
    return _XLSM[0]


# ── Idempotency ────────────────────────────────────────────────────────────────


def test_cpu_worker_skips_known_hash(real_file: Path) -> None:
    """File already in processed_hashes → CPUResult.skipped is True, no work done."""
    from api.pipeline.extractor import sha256_file

    known_hash = sha256_file(real_file)
    result = cpu_worker(real_file, {known_hash})

    assert result.skipped is True
    assert result.error is None
    assert result.domain is None
    assert result.lineage_events == []


def test_cpu_worker_unknown_hash_is_not_skipped(real_file: Path) -> None:
    """File not in processed_hashes → runs the full CPU pipeline."""
    result = cpu_worker(real_file, set())
    assert result.skipped is False


# ── Happy path ─────────────────────────────────────────────────────────────────


def test_cpu_worker_success_sets_all_fields(real_file: Path) -> None:
    """Happy path: domain, report, and raw_bytes are all populated."""
    result = cpu_worker(real_file, set())

    assert result.error is None
    assert result.domain is not None
    assert result.report is not None
    assert result.raw_bytes is not None
    assert len(result.raw_bytes) > 0
    assert result.duration_ms >= 0


def test_cpu_worker_success_emits_three_lineage_events(real_file: Path) -> None:
    """Happy path emits exactly source, extracted, and validated lineage events."""
    result = cpu_worker(real_file, set())
    stages = [evt.stage for evt in result.lineage_events]

    assert "source" in stages
    assert "extracted" in stages
    assert "validated" in stages
    assert len(result.lineage_events) == 3


def test_cpu_worker_success_all_lineage_events_succeeded(real_file: Path) -> None:
    result = cpu_worker(real_file, set())
    for evt in result.lineage_events:
        assert evt.status == "success", f"Event {evt.stage!r} has status {evt.status!r}"


# ── Missing sheet ──────────────────────────────────────────────────────────────


def test_cpu_worker_missing_sheet_sets_error(tmp_path: Path) -> None:
    """MissingSheetError → CPUResult.error is the exception message."""
    fake = tmp_path / "test.xlsm"
    fake.write_bytes(b"not a workbook")

    with (
        patch("api.pipeline.worker_cpu.sha256_file", return_value="abc123"),
        patch("api.pipeline.worker_cpu.MasterSheetExtractor") as mock_cls,
    ):
        mock_cls.return_value.extract.side_effect = MissingSheetError("No MASTER sheet")
        result = cpu_worker(fake, set())

    assert result.error == "No MASTER sheet"
    assert result.domain is None
    assert result.raw_bytes is None


def test_cpu_worker_missing_sheet_records_failed_lineage(tmp_path: Path) -> None:
    """The extracted lineage event is marked failed when the sheet is missing."""
    fake = tmp_path / "test.xlsm"
    fake.write_bytes(b"not a workbook")

    with (
        patch("api.pipeline.worker_cpu.sha256_file", return_value="abc123"),
        patch("api.pipeline.worker_cpu.MasterSheetExtractor") as mock_cls,
    ):
        mock_cls.return_value.extract.side_effect = MissingSheetError("No MASTER")
        result = cpu_worker(fake, set())

    failed = [e for e in result.lineage_events if e.stage == "extracted"]
    assert len(failed) == 1
    assert failed[0].status == "failed"


# ── Validation failure ─────────────────────────────────────────────────────────


def test_cpu_worker_validation_failure_sets_error(tmp_path: Path) -> None:
    """Validation errors → CPUResult.error == 'validation_errors', domain is None."""
    fake = tmp_path / "test.xlsm"
    fake.write_bytes(b"fake")

    mock_report = MagicMock()
    mock_report.passed = False
    mock_report.errors = [MagicMock(rule_id="R01")]
    mock_report.warnings = []

    with (
        patch("api.pipeline.worker_cpu.sha256_file", return_value="deadbeef"),
        patch("api.pipeline.worker_cpu.MasterSheetExtractor") as mock_cls,
        patch("api.pipeline.worker_cpu.validate", return_value=mock_report),
    ):
        mock_cls.return_value.extract.return_value = MagicMock()
        result = cpu_worker(fake, set())

    assert result.error == "validation_errors"
    assert result.domain is None
    assert result.report is mock_report


def test_cpu_worker_validation_failure_no_raw_bytes(tmp_path: Path) -> None:
    """raw_bytes is not read when validation fails — avoids unnecessary I/O."""
    fake = tmp_path / "test.xlsm"
    fake.write_bytes(b"fake")

    mock_report = MagicMock()
    mock_report.passed = False
    mock_report.errors = [MagicMock(rule_id="R05")]
    mock_report.warnings = []

    with (
        patch("api.pipeline.worker_cpu.sha256_file", return_value="deadbeef"),
        patch("api.pipeline.worker_cpu.MasterSheetExtractor") as mock_cls,
        patch("api.pipeline.worker_cpu.validate", return_value=mock_report),
    ):
        mock_cls.return_value.extract.return_value = MagicMock()
        result = cpu_worker(fake, set())

    assert result.raw_bytes is None


# ── Unexpected exception ───────────────────────────────────────────────────────


def test_cpu_worker_unexpected_exception_never_raises(tmp_path: Path) -> None:
    """Any unhandled exception inside the worker is caught and returned as error."""
    fake = tmp_path / "test.xlsm"
    fake.write_bytes(b"fake")

    with patch("api.pipeline.worker_cpu.sha256_file", side_effect=OSError("disk full")):
        result = cpu_worker(fake, set())

    assert result.error == "disk full"
    assert result.skipped is False
    assert result.domain is None


def test_cpu_worker_unexpected_exception_returns_cpu_result(tmp_path: Path) -> None:
    """Return type is always CPUResult regardless of exception type."""
    fake = tmp_path / "test.xlsm"
    fake.write_bytes(b"fake")

    with patch("api.pipeline.worker_cpu.sha256_file", side_effect=RuntimeError("boom")):
        result = cpu_worker(fake, set())

    assert isinstance(result, CPUResult)
