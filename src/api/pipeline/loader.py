"""
Load a DomainRecord into the database within a single transaction.

SCD2 close-out:
  1. Set valid_to = NOW() on the current open snapshot for the company.
  2. Insert a new snapshot with valid_to = NULL (the new current record).
  3. Insert child rows (segments, metrics).
  4. Insert upload_audit + upload_file_store.
  5. Commit everything atomically.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from api.models.orm import (
    DimCompany,
    FactCompanySnapshot,
    FactCreditMetric,
    FactIndustrySegment,
    UploadAudit,
    UploadFileStore,
)
from api.pipeline.transformer import DomainRecord
from api.pipeline.validator import ValidationReport

log = logging.getLogger(__name__)


def load(
        session: Session,
        domain: DomainRecord,
        report: ValidationReport,
        raw_bytes: bytes,
        filename: str,
        file_sha256: str,
        run_id: str,
) -> tuple[int, int]:
    """Load one file. Returns (upload_id, snapshot_id)."""
    now = datetime.now(timezone.utc)

    # ── 1. Upsert dim_company ──────────────────────────────────────────
    company = (
        session.query(DimCompany)
        .filter(DimCompany.entity_name == domain.entity_name)
        .one_or_none()
    )
    if company is None:
        company = DimCompany(entity_name=domain.entity_name, created_at=now)
        session.add(company)
        session.flush()

    # ── 2. Insert upload_audit ─────────────────────────────────────────
    validation_status = (
        "passed" if (report.passed and not report.warnings)
        else "passed_with_warnings" if report.passed
        else "failed"
    )
    audit = UploadAudit(
        filename=filename,
        file_sha256=file_sha256,
        uploaded_at=now,
        pipeline_run_id=run_id,
        byte_size=len(raw_bytes),
        validation_status=validation_status,
        validation_report=report.to_dict(),
    )
    session.add(audit)
    session.flush()

    # ── 3. Store raw bytes ─────────────────────────────────────────────
    session.add(UploadFileStore(upload_id=audit.id, raw_bytes=raw_bytes))

    # ── 4. SCD2 close-out ─────────────────────────────────────────────
    open_snapshot = (
        session.query(FactCompanySnapshot)
        .filter(
            FactCompanySnapshot.company_id == company.id,
            FactCompanySnapshot.valid_to.is_(None),
        )
        .one_or_none()
    )
    next_version = 1
    if open_snapshot is not None:
        open_snapshot.valid_to = now
        next_version = open_snapshot.version_number + 1
        session.flush()

    # ── 5. Insert new snapshot ─────────────────────────────────────────
    snapshot = FactCompanySnapshot(
        company_id=company.id,
        upload_id=audit.id,
        version_number=next_version,
        valid_from=now,
        valid_to=None,
        corporate_sector=domain.corporate_sector,
        reporting_currency=domain.reporting_currency,
        country_of_origin=domain.country_of_origin,
        accounting_principles=domain.accounting_principles,
        business_year_end_month=domain.business_year_end_month,
        segmentation_criteria=domain.segmentation_criteria,
        business_risk_profile=domain.business_risk_profile,
        blended_industry_risk_profile=domain.blended_industry_risk_profile,
        competitive_positioning=domain.competitive_positioning,
        market_share=domain.market_share,
        diversification=domain.diversification,
        operating_profitability=domain.operating_profitability,
        sector_specific_factor_1=domain.sector_specific_factor_1,
        sector_specific_factor_2=domain.sector_specific_factor_2,
        financial_risk_profile=domain.financial_risk_profile,
        leverage=domain.leverage,
        interest_cover=domain.interest_cover,
        cash_flow_cover=domain.cash_flow_cover,
        liquidity_adjustment=domain.liquidity_adjustment,
        rating_methodologies=domain.rating_methodologies or [],
    )
    session.add(snapshot)
    session.flush()

    # ── 6. Insert segments ─────────────────────────────────────────────
    for seg in domain.industry_segments:
        session.add(
            FactIndustrySegment(
                snapshot_id=snapshot.id,
                segment_index=seg.index,
                industry_name=seg.industry_name,
                risk_score=seg.risk_score,
                weight=seg.weight,
            )
        )

    # ── 7. Insert credit metrics ───────────────────────────────────────
    for m in domain.credit_metrics:
        session.add(
            FactCreditMetric(
                snapshot_id=snapshot.id,
                metric_year=m.year,
                ebitda_interest_cover=m.ebitda_interest_cover,
                debt_ebitda=m.debt_ebitda,
                ffo_debt=m.ffo_debt,
                loan_value=m.loan_value,
                focf_debt=m.focf_debt,
                liquidity=m.liquidity,
            )
        )

    session.commit()
    log.info(
        "Loaded %s: company_id=%d upload_id=%d snapshot_id=%d version=%d",
        filename, company.id, audit.id, snapshot.id, next_version,
    )
    return audit.id, snapshot.id
