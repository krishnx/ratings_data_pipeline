"""
I/O-bound pipeline stage: write DB records and lineage.

Runs in a thread via ThreadPoolExecutor. Each thread owns its own Session.
Consumes CPUResult objects from a shared queue.Queue until it receives
STOP_SENTINEL.
"""

from __future__ import annotations

import logging
import queue
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from api.models.orm import DataLineage
from api.pipeline.loader import load
from api.pipeline.worker_cpu import CPUResult, LineageEvent

log = logging.getLogger(__name__)


class _StopSentinel:
    """Poison-pill: each io_consumer exits when it dequeues this."""


STOP_SENTINEL = _StopSentinel()


def io_consumer(
    result_queue: queue.Queue[CPUResult | _StopSentinel],
    session_factory: sessionmaker[Session],
    per_file: list[dict[str, Any]],
    run_id: str,
) -> None:
    """
    Drain result_queue until STOP_SENTINEL is received.

    list.append is GIL-safe in CPython so per_file can be shared across
    multiple io_consumer threads without a lock.
    """
    while True:
        item = result_queue.get()
        try:
            if isinstance(item, _StopSentinel):
                return
            _process_cpu_result(item, session_factory, per_file, run_id)
        finally:
            result_queue.task_done()


def _process_cpu_result(
    cpu: CPUResult,
    session_factory: sessionmaker[Session],
    per_file: list[dict[str, Any]],
    run_id: str,
) -> None:
    if cpu.skipped:
        log.info("Skipping %s (already processed)", cpu.filename)
        per_file.append({"file": cpu.filename, "status": "skipped", "reason": "already_processed"})
        return

    session: Session = session_factory()
    lineage_id = str(uuid.uuid4())
    try:
        _write_lineage_events(session, lineage_id, cpu.lineage_events)

        if cpu.error == "validation_errors" and cpu.report is not None:
            session.commit()
            per_file.append(
                {
                    "file": cpu.filename,
                    "status": "failed",
                    "reason": "validation_errors",
                    "errors": [r.rule_id for r in cpu.report.errors],
                }
            )
            return

        if cpu.error is not None:
            session.commit()
            per_file.append({"file": cpu.filename, "status": "failed", "reason": cpu.error})
            return

        # Happy path — all three payloads must be set
        if cpu.domain is None or cpu.report is None or cpu.raw_bytes is None:
            session.commit()
            per_file.append({"file": cpu.filename, "status": "failed", "reason": "internal_error"})
            return

        upload_id, snapshot_id = load(
            session,
            cpu.domain,
            cpu.report,
            cpu.raw_bytes,
            cpu.filename,
            cpu.file_sha256,
            run_id,
        )

        _write_loaded_lineage(session, lineage_id, cpu.file_sha256, upload_id, snapshot_id)
        session.commit()

        validation_status = "passed_with_warnings" if cpu.report.warnings else "passed"
        per_file.append(
            {
                "file": cpu.filename,
                "status": "processed",
                "validation": validation_status,
                "industry_segments": len(cpu.domain.industry_segments),
                "credit_metric_years": len(cpu.domain.credit_metrics),
                "duration_ms": cpu.duration_ms,
            }
        )
        log.info("Loaded %s (%dms cpu)", cpu.filename, cpu.duration_ms)

    except Exception as exc:
        session.rollback()
        log.exception("I/O stage failed for %s: %s", cpu.filename, exc)
        per_file.append({"file": cpu.filename, "status": "failed", "reason": str(exc)})
    finally:
        session.close()


def _write_lineage_events(
    session: Session,
    lineage_id: str,
    events: list[LineageEvent],
) -> None:
    now = datetime.now(timezone.utc)
    for evt in events:
        session.add(
            DataLineage(
                lineage_id=lineage_id,
                stage=evt.stage,
                source_ref=evt.source_ref,
                target_ref=evt.target_ref,
                stage_status=evt.status,
                occurred_at=now,
                extra=evt.metadata,
            )
        )
    session.flush()


def _write_loaded_lineage(
    session: Session,
    lineage_id: str,
    file_sha256: str,
    upload_id: int,
    snapshot_id: int,
) -> None:
    session.add(
        DataLineage(
            lineage_id=lineage_id,
            stage="loaded",
            source_ref=file_sha256,
            target_ref=f"snapshot_id={snapshot_id}",
            stage_status="success",
            upload_id=upload_id,
            snapshot_id=snapshot_id,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
