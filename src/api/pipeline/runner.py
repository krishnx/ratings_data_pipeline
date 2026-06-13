"""
Pipeline orchestration: scan data dir → hash → extract → validate → transform → load.

Idempotency: files whose SHA-256 is already in upload_audit are skipped.
Retry: transient DB errors retry up to MAX_ATTEMPTS times with exponential backoff.
State: pipeline_state table records each run's outcome.
Lineage: data_lineage table records each stage per file.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from api.models.orm import DataLineage, PipelineState, UploadAudit
from api.pipeline.constants import BASE_DELAY_S, MAX_ATTEMPTS
from api.pipeline.exceptions import MissingSheetError
from api.pipeline.extractor import MasterSheetExtractor, sha256_file
from api.pipeline.loader import load
from api.pipeline.transformer import transform
from api.pipeline.utils import retry
from api.pipeline.validator import validate

log = logging.getLogger(__name__)


def _record_lineage(
    session: Session,
    lineage_id: str,
    stage: str,
    source_ref: str,
    target_ref: str | None,
    status: str,
    upload_id: int | None = None,
    snapshot_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    entry = DataLineage(
        lineage_id=lineage_id,
        stage=stage,
        source_ref=source_ref,
        target_ref=target_ref,
        stage_status=status,
        upload_id=upload_id,
        snapshot_id=snapshot_id,
        occurred_at=datetime.now(timezone.utc),
        extra=metadata,
    )
    session.add(entry)
    session.flush()


def _get_processed_hashes(session: Session) -> set[str]:
    rows = session.query(UploadAudit.file_sha256).all()
    return {r.file_sha256 for r in rows}


def _refresh_materialized_views(session: Session) -> None:
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

    extractor = MasterSheetExtractor()
    per_file: list[dict[str, Any]] = []
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    error_summary: list[dict[str, Any]] = []

    # Record pipeline run as 'running'
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
        ps_id = ps.id
    finally:
        state_session.close()

    for path in files:
        filename = path.name
        file_start_ms = time.monotonic()
        lineage_id = str(uuid.uuid4())

        session: Session = session_factory()
        try:
            processed_hashes = _get_processed_hashes(session)
            file_sha256 = sha256_file(path)

            if file_sha256 in processed_hashes:
                log.info("Skipping %s (already processed)", filename)
                per_file.append({"file": filename, "status": "skipped", "reason": "already_processed"})
                files_skipped += 1
                continue

            # source stage
            _record_lineage(
                session,
                lineage_id,
                stage="source",
                source_ref=str(path),
                target_ref=file_sha256,
                status="success",
            )
            session.commit()

            # extract
            try:
                raw = extractor.extract(path)
            except MissingSheetError as exc:
                log.warning("Extraction failed for %s: %s", filename, exc)
                _record_lineage(
                    session,
                    lineage_id,
                    stage="extracted",
                    source_ref=file_sha256,
                    target_ref=None,
                    status="failed",
                    metadata={"error": str(exc)},
                )
                session.commit()
                per_file.append({"file": filename, "status": "failed", "reason": str(exc)})
                files_failed += 1
                error_summary.append({"file": filename, "error": str(exc)})
                continue

            _record_lineage(
                session,
                lineage_id,
                stage="extracted",
                source_ref=file_sha256,
                target_ref=f"segments={len(raw.industry_segments)},years={len(raw.credit_metrics)}",
                status="success",
                metadata={"entity_name": raw.entity_name},
            )
            session.commit()

            # validate
            report = validate(raw)
            _record_lineage(
                session,
                lineage_id,
                stage="validated",
                source_ref=file_sha256,
                target_ref="passed" if report.passed else "failed",
                status="success" if report.passed else "failed",
                metadata={"errors": len(report.errors), "warnings": len(report.warnings)},
            )
            session.commit()

            if not report.passed:
                log.warning("Validation errors in %s — skipping load", filename)
                per_file.append(
                    {
                        "file": filename,
                        "status": "failed",
                        "reason": "validation_errors",
                        "errors": [r.rule_id for r in report.errors],
                    }
                )
                files_failed += 1
                error_summary.append({"file": filename, "errors": [r.rule_id for r in report.errors]})
                continue

            # transform + load (with retry)
            domain = transform(raw)
            raw_bytes = path.read_bytes()

            @retry(
                OperationalError,
                max_attempts=MAX_ATTEMPTS,
                base_delay_s=BASE_DELAY_S,
                on_retry=lambda _: session.rollback(),
            )
            def _load_with_retry() -> tuple[int, int]:
                return load(session, domain, report, raw_bytes, filename, file_sha256, run_id)

            upload_id, snapshot_id = _load_with_retry()

            _record_lineage(
                session,
                lineage_id,
                stage="loaded",
                source_ref=file_sha256,
                target_ref=f"snapshot_id={snapshot_id}",
                status="success",
                upload_id=upload_id,
                snapshot_id=snapshot_id,
            )
            session.commit()

            duration_ms = int((time.monotonic() - file_start_ms) * 1000)
            validation_status = "passed_with_warnings" if report.warnings else "passed"
            per_file.append(
                {
                    "file": filename,
                    "status": "processed",
                    "validation": validation_status,
                    "industry_segments": len(domain.industry_segments),
                    "credit_metric_years": len(domain.credit_metrics),
                    "duration_ms": duration_ms,
                }
            )
            files_processed += 1
            log.info("Processed %s in %dms", filename, duration_ms)

        except Exception as exc:
            session.rollback()
            log.exception("Unexpected error processing %s: %s", filename, exc)
            per_file.append({"file": filename, "status": "failed", "reason": str(exc)})
            files_failed += 1
            error_summary.append({"file": filename, "error": str(exc)})
        finally:
            session.close()

    total_duration_ms = int((time.monotonic() - started_ms) * 1000)
    finished_at = datetime.now(timezone.utc)

    final_status = "success" if files_failed == 0 else "partial" if files_processed > 0 else "failed"

    # Update pipeline_state
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

    result = {
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
