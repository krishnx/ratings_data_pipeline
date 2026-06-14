"""
CPU-bound pipeline stages: hash → idempotency check → extract → validate → transform.

Runs in a subprocess via ProcessPoolExecutor. No DB access, no sessions.
All inputs and outputs are plain Python dataclasses (fully picklable).
"""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import Any

from api.pipeline.exceptions import MissingSheetError
from api.pipeline.extractor import MasterSheetExtractor, sha256_file
from api.pipeline.transformer import DomainRecord, transform
from api.pipeline.validator import ValidationReport, validate


@dataclasses.dataclass
class LineageEvent:
    """One lineage stage record carried back to the I/O thread for DB write."""

    stage: str
    source_ref: str
    target_ref: str | None
    status: str
    metadata: dict[str, Any] | None = None


@dataclasses.dataclass
class CPUResult:
    """
    Returned by cpu_worker — fully picklable, no DB objects.

    Invariants:
      skipped=True         → only path/filename/file_sha256 are meaningful
      error is not None    → domain/report/raw_bytes may be None
      error is None        → domain/report/raw_bytes are all set
    """

    path: Path
    filename: str
    file_sha256: str
    domain: DomainRecord | None
    report: ValidationReport | None
    raw_bytes: bytes | None
    lineage_events: list[LineageEvent]
    error: str | None = None
    skipped: bool = False
    duration_ms: int = 0


def cpu_worker(path: Path, processed_hashes: set[str]) -> CPUResult:
    """
    Execute CPU-bound pipeline stages for one file.

    Never raises — all exceptions are captured in CPUResult.error so the
    caller (main thread) always gets a result back through the queue.
    """
    t0 = time.monotonic()
    filename = path.name
    lineage_events: list[LineageEvent] = []

    try:
        file_sha256 = sha256_file(path)

        if file_sha256 in processed_hashes:
            return CPUResult(
                path=path,
                filename=filename,
                file_sha256=file_sha256,
                domain=None,
                report=None,
                raw_bytes=None,
                lineage_events=[],
                skipped=True,
            )

        lineage_events.append(
            LineageEvent(
                stage="source",
                source_ref=str(path),
                target_ref=file_sha256,
                status="success",
            )
        )

        try:
            raw = MasterSheetExtractor().extract(path)
        except MissingSheetError as exc:
            lineage_events.append(
                LineageEvent(
                    stage="extracted",
                    source_ref=file_sha256,
                    target_ref=None,
                    status="failed",
                    metadata={"error": str(exc)},
                )
            )
            return CPUResult(
                path=path,
                filename=filename,
                file_sha256=file_sha256,
                domain=None,
                report=None,
                raw_bytes=None,
                lineage_events=lineage_events,
                error=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        lineage_events.append(
            LineageEvent(
                stage="extracted",
                source_ref=file_sha256,
                target_ref=f"segments={len(raw.industry_segments)},years={len(raw.credit_metrics)}",
                status="success",
                metadata={"entity_name": raw.entity_name},
            )
        )

        report = validate(raw)
        lineage_events.append(
            LineageEvent(
                stage="validated",
                source_ref=file_sha256,
                target_ref="passed" if report.passed else "failed",
                status="success" if report.passed else "failed",
                metadata={"errors": len(report.errors), "warnings": len(report.warnings)},
            )
        )

        if not report.passed:
            return CPUResult(
                path=path,
                filename=filename,
                file_sha256=file_sha256,
                domain=None,
                report=report,
                raw_bytes=None,
                lineage_events=lineage_events,
                error="validation_errors",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        domain = transform(raw)
        raw_bytes = path.read_bytes()

        return CPUResult(
            path=path,
            filename=filename,
            file_sha256=file_sha256,
            domain=domain,
            report=report,
            raw_bytes=raw_bytes,
            lineage_events=lineage_events,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    except Exception as exc:
        return CPUResult(
            path=path,
            filename=filename,
            file_sha256="",
            domain=None,
            report=None,
            raw_bytes=None,
            lineage_events=lineage_events,
            error=str(exc),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
