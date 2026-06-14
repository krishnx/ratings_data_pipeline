"""
Pipeline orchestration: scan data dir → parallel CPU stages → parallel I/O stages.

Architecture (two-pool producer-consumer):
  ProcessPoolExecutor  — hash, extract, validate, transform (CPU-bound, bypasses GIL)
      ↓  queue.Queue (bounded, provides backpressure)
  ThreadPoolExecutor   — load, lineage write, commit   (I/O-bound, owns DB sessions)

Idempotency: processed SHA-256 hashes are fetched once before the pools start;
             files already in upload_audit are skipped in the CPU worker.
State:       pipeline_state table records each run's outcome.
Retry:       transient DB errors in the I/O stage are handled by the existing
             retry decorator inside loader.load().
"""

from __future__ import annotations

import logging
import multiprocessing
import queue
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from api.config import settings
from api.models.orm import PipelineState, UploadAudit
from api.pipeline.worker_cpu import CPUResult, cpu_worker
from api.pipeline.worker_io import STOP_SENTINEL, _StopSentinel, io_consumer

log = logging.getLogger(__name__)

# ── Concurrency configuration ──────────────────────────────────────────────────
# Resolved once at import time from settings (env vars PIPELINE_CPU_WORKERS /
# PIPELINE_IO_WORKERS override the defaults defined in config.py).
_CPU_WORKERS: int = settings.pipeline_cpu_workers
_IO_WORKERS: int = settings.pipeline_io_workers
# Queue depth: allow the CPU pool to get this many results ahead of the I/O pool.
_QUEUE_SIZE: int = _IO_WORKERS * 3


def _get_processed_hashes(session: Session) -> set[str]:
    rows = session.query(UploadAudit.file_sha256).all()
    return {r.file_sha256 for r in rows}


def _refresh_materialized_views(session: Session) -> None:
    # mv_analytics_summary depends on mv_current_snapshots → must refresh in order
    try:
        session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_current_snapshots"))
        session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_analytics_summary"))
        session.commit()
    except Exception as exc:
        log.warning("Could not refresh materialized views: %s", exc)
        session.rollback()


def run_pipeline(data_dir: str, session_factory: sessionmaker[Session]) -> dict[str, Any]:
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    started_at = datetime.now(timezone.utc)
    started_ms = time.monotonic()

    files = sorted(Path(data_dir).glob("*.xlsm"))
    files_found = len(files)

    # ── Record pipeline run as 'running' ───────────────────────────────────────
    state_session: Session = session_factory()
    try:
        ps = PipelineState(
            run_id=run_id,
            started_at=started_at,
            status="running",
            files_found=files_found,
        )
        state_session.add(ps)
        state_session.commit()
        ps_id: int = ps.id
    finally:
        state_session.close()

    # ── Pre-fetch processed hashes — one query, shared across all CPU workers ──
    hash_session: Session = session_factory()
    try:
        processed_hashes = _get_processed_hashes(hash_session)
    finally:
        hash_session.close()

    per_file: list[dict[str, Any]] = []

    if files:
        result_queue: queue.Queue[CPUResult | _StopSentinel] = queue.Queue(maxsize=_QUEUE_SIZE)

        with ThreadPoolExecutor(max_workers=_IO_WORKERS) as io_pool:
            io_futures = [
                io_pool.submit(io_consumer, result_queue, session_factory, per_file, run_id)
                for _ in range(_IO_WORKERS)
            ]

            # Use spawn context explicitly: avoids fork-inherited DB connections on Linux
            mp_ctx = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(max_workers=_CPU_WORKERS, mp_context=mp_ctx) as cpu_pool:
                futures = {
                    cpu_pool.submit(cpu_worker, path, processed_hashes): path for path in files
                }
                for future in as_completed(futures):
                    try:
                        result_queue.put(future.result())  # blocks when queue is full
                    except Exception as exc:
                        crashed_path = futures[future]
                        log.exception("CPU worker crashed for %s: %s", crashed_path.name, exc)
                        per_file.append(
                            {"file": crashed_path.name, "status": "failed", "reason": str(exc)}
                        )

            # Signal each I/O worker to stop, then wait for the queue to drain
            for _ in range(_IO_WORKERS):
                result_queue.put(STOP_SENTINEL)
            result_queue.join()

            # Surface any unexpected I/O worker exceptions
            for io_fut in io_futures:
                io_exc = io_fut.exception()
                if io_exc is not None:
                    log.error("I/O worker raised unexpectedly: %s", io_exc)

    # ── Compute final counts from per_file (populated by I/O workers) ──────────
    files_processed = sum(1 for r in per_file if r["status"] == "processed")
    files_skipped = sum(1 for r in per_file if r["status"] == "skipped")
    files_failed = sum(1 for r in per_file if r["status"] == "failed")
    error_summary: list[dict[str, Any]] = [
        {"file": r["file"], "error": r.get("reason", "unknown")}
        for r in per_file
        if r["status"] == "failed"
    ]

    total_duration_ms = int((time.monotonic() - started_ms) * 1000)
    finished_at = datetime.now(timezone.utc)
    final_status = (
        "success" if files_failed == 0 else "partial" if files_processed > 0 else "failed"
    )

    # ── Update pipeline_state ──────────────────────────────────────────────────
    state_session = session_factory()
    try:
        ps_row = state_session.query(PipelineState).filter(PipelineState.id == ps_id).one()
        ps_row.finished_at = finished_at
        ps_row.status = final_status
        ps_row.files_processed = files_processed
        ps_row.files_skipped = files_skipped
        ps_row.files_failed = files_failed
        ps_row.total_duration_ms = total_duration_ms
        ps_row.error_summary = error_summary or None
        state_session.commit()
        _refresh_materialized_views(state_session)
    finally:
        state_session.close()

    result: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "total_duration_ms": total_duration_ms,
        "files_found": files_found,
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "files_failed": files_failed,
        "status": final_status,
        "per_file": per_file,
    }
    log.info("Pipeline complete: %s", result)
    return result
