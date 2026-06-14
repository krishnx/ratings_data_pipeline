"""
Unit tests for the I/O pipeline consumer.

io_consumer() is tested in-process via a real queue.Queue with mocked DB
sessions and a mocked load() function.
"""

import queue
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from api.pipeline.worker_cpu import CPUResult, LineageEvent
from api.pipeline.worker_io import STOP_SENTINEL, io_consumer


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_cpu_result(**overrides: Any) -> CPUResult:
    defaults: dict[str, Any] = dict(
        path=Path("/data/test.xlsm"),
        filename="test.xlsm",
        file_sha256="abc123",
        domain=None,
        report=None,
        raw_bytes=None,
        lineage_events=[],
        error=None,
        skipped=False,
        duration_ms=0,
    )
    defaults.update(overrides)
    return CPUResult(**defaults)


def _mock_session_factory() -> MagicMock:
    factory = MagicMock()
    session = MagicMock()
    factory.return_value = session
    return factory


def _run_consumer(items: list[Any]) -> list[dict[str, Any]]:
    """Put items + STOP_SENTINEL in a queue, run io_consumer, return per_file."""
    q: queue.Queue[Any] = queue.Queue()
    for item in items:
        q.put(item)
    q.put(STOP_SENTINEL)

    per_file: list[dict[str, Any]] = []
    io_consumer(q, _mock_session_factory(), per_file, run_id="run_test")
    q.join()
    return per_file


# ── Stop sentinel ──────────────────────────────────────────────────────────────


def test_io_consumer_stops_on_sentinel() -> None:
    """Consumer exits immediately on STOP_SENTINEL; per_file is empty."""
    q: queue.Queue[Any] = queue.Queue()
    q.put(STOP_SENTINEL)
    per_file: list[dict[str, Any]] = []
    io_consumer(q, _mock_session_factory(), per_file, run_id="run_test")
    q.join()
    assert per_file == []


def test_io_consumer_processes_items_before_sentinel() -> None:
    """Items queued before the sentinel are fully processed."""
    cpu = _make_cpu_result(skipped=True)
    results = _run_consumer([cpu])
    assert len(results) == 1


# ── Skipped files ──────────────────────────────────────────────────────────────


def test_io_consumer_skipped_file_appends_skipped_status() -> None:
    cpu = _make_cpu_result(skipped=True)
    results = _run_consumer([cpu])
    assert results[0]["status"] == "skipped"
    assert results[0]["reason"] == "already_processed"


def test_io_consumer_skipped_file_does_not_open_session() -> None:
    """Skipped files never touch the DB."""
    cpu = _make_cpu_result(skipped=True)
    factory = _mock_session_factory()
    q: queue.Queue[Any] = queue.Queue()
    q.put(cpu)
    q.put(STOP_SENTINEL)
    per_file: list[dict[str, Any]] = []
    io_consumer(q, factory, per_file, run_id="run_test")
    q.join()
    factory.assert_not_called()


# ── Generic CPU error ──────────────────────────────────────────────────────────


def test_io_consumer_generic_error_appends_failed() -> None:
    cpu = _make_cpu_result(error="Cannot open file: permission denied")
    results = _run_consumer([cpu])
    assert results[0]["status"] == "failed"
    assert "permission denied" in results[0]["reason"]


# ── Validation failure ─────────────────────────────────────────────────────────


def test_io_consumer_validation_failure_appends_failed_with_rule_ids() -> None:
    mock_report = MagicMock()
    mock_report.passed = False
    mock_report.errors = [MagicMock(rule_id="R01"), MagicMock(rule_id="R05")]
    cpu = _make_cpu_result(error="validation_errors", report=mock_report)
    results = _run_consumer([cpu])

    assert results[0]["status"] == "failed"
    assert results[0]["reason"] == "validation_errors"
    assert "R01" in results[0]["errors"]
    assert "R05" in results[0]["errors"]


def test_io_consumer_validation_failure_without_report_still_returns_failed() -> None:
    """error='validation_errors' but report=None → treated as generic failure."""
    cpu = _make_cpu_result(error="validation_errors", report=None)
    results = _run_consumer([cpu])
    assert results[0]["status"] == "failed"


# ── Happy path ─────────────────────────────────────────────────────────────────


def test_io_consumer_success_calls_load() -> None:
    """Happy path: load() is called exactly once with the right run_id."""
    mock_domain = MagicMock()
    mock_domain.industry_segments = [MagicMock()]
    mock_domain.credit_metrics = [MagicMock(), MagicMock()]

    mock_report = MagicMock()
    mock_report.passed = True
    mock_report.errors = []
    mock_report.warnings = []

    cpu = _make_cpu_result(
        domain=mock_domain,
        report=mock_report,
        raw_bytes=b"xlsm-bytes",
        error=None,
        lineage_events=[LineageEvent("source", "/data/test.xlsm", "abc123", "success")],
    )

    with (
        patch("api.pipeline.worker_io.load", return_value=(1, 10)) as mock_load,
        patch("api.pipeline.worker_io._write_lineage_events"),
        patch("api.pipeline.worker_io._write_loaded_lineage"),
    ):
        _run_consumer([cpu])

    mock_load.assert_called_once()
    call_kwargs = mock_load.call_args
    assert call_kwargs.args[4] == "test.xlsm"  # filename positional arg
    assert call_kwargs.args[6] == "run_test"   # run_id positional arg


def test_io_consumer_success_appends_processed_entry() -> None:
    mock_domain = MagicMock()
    mock_domain.industry_segments = [MagicMock(), MagicMock()]
    mock_domain.credit_metrics = [MagicMock()]

    mock_report = MagicMock()
    mock_report.passed = True
    mock_report.errors = []
    mock_report.warnings = []

    cpu = _make_cpu_result(
        domain=mock_domain,
        report=mock_report,
        raw_bytes=b"data",
        error=None,
        duration_ms=123,
    )

    with (
        patch("api.pipeline.worker_io.load", return_value=(2, 20)),
        patch("api.pipeline.worker_io._write_lineage_events"),
        patch("api.pipeline.worker_io._write_loaded_lineage"),
    ):
        results = _run_consumer([cpu])

    assert results[0]["status"] == "processed"
    assert results[0]["industry_segments"] == 2
    assert results[0]["credit_metric_years"] == 1
    assert results[0]["duration_ms"] == 123


def test_io_consumer_success_with_warnings_sets_validation_status() -> None:
    mock_domain = MagicMock()
    mock_domain.industry_segments = []
    mock_domain.credit_metrics = []

    mock_report = MagicMock()
    mock_report.passed = True
    mock_report.errors = []
    mock_report.warnings = [MagicMock(rule_id="R15")]

    cpu = _make_cpu_result(
        domain=mock_domain,
        report=mock_report,
        raw_bytes=b"data",
        error=None,
    )

    with (
        patch("api.pipeline.worker_io.load", return_value=(3, 30)),
        patch("api.pipeline.worker_io._write_lineage_events"),
        patch("api.pipeline.worker_io._write_loaded_lineage"),
    ):
        results = _run_consumer([cpu])

    assert results[0]["validation"] == "passed_with_warnings"


# ── DB exception recovery ──────────────────────────────────────────────────────


def test_io_consumer_db_exception_appends_failed_and_rolls_back() -> None:
    """A DB exception in load() causes a rollback and a 'failed' per_file entry."""
    mock_domain = MagicMock()
    mock_domain.industry_segments = []
    mock_domain.credit_metrics = []

    mock_report = MagicMock()
    mock_report.passed = True
    mock_report.errors = []
    mock_report.warnings = []

    cpu = _make_cpu_result(
        domain=mock_domain,
        report=mock_report,
        raw_bytes=b"data",
        error=None,
    )

    factory = _mock_session_factory()
    q: queue.Queue[Any] = queue.Queue()
    q.put(cpu)
    q.put(STOP_SENTINEL)
    per_file: list[dict[str, Any]] = []

    with (
        patch("api.pipeline.worker_io.load", side_effect=RuntimeError("DB down")),
        patch("api.pipeline.worker_io._write_lineage_events"),
    ):
        io_consumer(q, factory, per_file, run_id="run_test")
    q.join()

    assert per_file[0]["status"] == "failed"
    assert "DB down" in per_file[0]["reason"]
    factory.return_value.rollback.assert_called_once()  # session rolled back


# ── Multiple files ─────────────────────────────────────────────────────────────


def test_io_consumer_processes_multiple_items_in_order() -> None:
    """All items queued before the sentinel are processed; order is preserved."""
    items = [_make_cpu_result(filename=f"file_{i}.xlsm", skipped=True) for i in range(3)]
    results = _run_consumer(items)
    assert len(results) == 3
    assert [r["file"] for r in results] == ["file_0.xlsm", "file_1.xlsm", "file_2.xlsm"]
