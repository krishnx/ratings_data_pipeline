from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Timezone-aware timestamp (maps to TIMESTAMPTZ in PostgreSQL)
TIMESTAMPTZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class DimCompany(Base):
    __tablename__ = "dim_company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_name: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)

    snapshots: Mapped[list[FactCompanySnapshot]] = relationship("FactCompanySnapshot", back_populates="company")


class UploadAudit(Base):
    __tablename__ = "upload_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(Text, unique=True)
    uploaded_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    pipeline_run_id: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    validation_status: Mapped[str] = mapped_column(Text)
    validation_report: Mapped[Any] = mapped_column(JSONB)

    file_store: Mapped[UploadFileStore | None] = relationship("UploadFileStore", back_populates="upload", uselist=False)
    snapshots: Mapped[list[FactCompanySnapshot]] = relationship("FactCompanySnapshot", back_populates="upload")
    lineage: Mapped[list[DataLineage]] = relationship("DataLineage", back_populates="upload")


class UploadFileStore(Base):
    __tablename__ = "upload_file_store"

    upload_id: Mapped[int] = mapped_column(Integer, ForeignKey("upload_audit.id", ondelete="CASCADE"), primary_key=True)
    raw_bytes: Mapped[bytes] = mapped_column(LargeBinary)

    upload: Mapped[UploadAudit] = relationship("UploadAudit", back_populates="file_store")


class FactCompanySnapshot(Base):
    __tablename__ = "fact_company_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("dim_company.id"))
    upload_id: Mapped[int] = mapped_column(Integer, ForeignKey("upload_audit.id"))
    version_number: Mapped[int] = mapped_column(Integer)

    valid_from: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)

    corporate_sector: Mapped[str | None] = mapped_column(Text)
    reporting_currency: Mapped[str | None] = mapped_column(Text)
    country_of_origin: Mapped[str | None] = mapped_column(Text)
    accounting_principles: Mapped[str | None] = mapped_column(Text)
    business_year_end_month: Mapped[str | None] = mapped_column(Text)
    segmentation_criteria: Mapped[str | None] = mapped_column(Text)

    business_risk_profile: Mapped[str | None] = mapped_column(Text)
    blended_industry_risk_profile: Mapped[str | None] = mapped_column(Text)
    competitive_positioning: Mapped[str | None] = mapped_column(Text)
    market_share: Mapped[str | None] = mapped_column(Text)
    diversification: Mapped[str | None] = mapped_column(Text)
    operating_profitability: Mapped[str | None] = mapped_column(Text)
    sector_specific_factor_1: Mapped[str | None] = mapped_column(Text)
    sector_specific_factor_2: Mapped[str | None] = mapped_column(Text)
    financial_risk_profile: Mapped[str | None] = mapped_column(Text)
    leverage: Mapped[str | None] = mapped_column(Text)
    interest_cover: Mapped[str | None] = mapped_column(Text)
    cash_flow_cover: Mapped[str | None] = mapped_column(Text)
    liquidity_adjustment: Mapped[str | None] = mapped_column(Text)

    rating_methodologies: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    raw_extras: Mapped[Any] = mapped_column(JSONB)
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english',"
            " COALESCE(corporate_sector, '') || ' ' ||"
            " COALESCE(country_of_origin, '') || ' ' ||"
            " COALESCE(business_risk_profile, '') || ' ' ||"
            " COALESCE(financial_risk_profile, '') || ' ' ||"
            " COALESCE(blended_industry_risk_profile, ''))",
            persisted=True,
        ),
    )

    company: Mapped[DimCompany] = relationship("DimCompany", back_populates="snapshots")
    upload: Mapped[UploadAudit] = relationship("UploadAudit", back_populates="snapshots")
    industry_segments: Mapped[list[FactIndustrySegment]] = relationship(
        "FactIndustrySegment",
        back_populates="snapshot",
        order_by="FactIndustrySegment.segment_index",
        cascade="all, delete-orphan",
    )
    credit_metrics: Mapped[list[FactCreditMetric]] = relationship(
        "FactCreditMetric",
        back_populates="snapshot",
        order_by="FactCreditMetric.metric_year",
        cascade="all, delete-orphan",
    )


class FactIndustrySegment(Base):
    __tablename__ = "fact_industry_segment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("fact_company_snapshot.id", ondelete="CASCADE"))
    segment_index: Mapped[int] = mapped_column(SmallInteger)
    industry_name: Mapped[str] = mapped_column(Text)
    risk_score: Mapped[str] = mapped_column(Text)
    weight: Mapped[float] = mapped_column(Numeric(6, 4))

    snapshot: Mapped[FactCompanySnapshot] = relationship("FactCompanySnapshot", back_populates="industry_segments")

    __table_args__ = (UniqueConstraint("snapshot_id", "segment_index", name="uq_segment_snapshot_idx"),)


class FactCreditMetric(Base):
    __tablename__ = "fact_credit_metric"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("fact_company_snapshot.id", ondelete="CASCADE"))
    metric_year: Mapped[int] = mapped_column(SmallInteger)
    ebitda_interest_cover: Mapped[float | None] = mapped_column(Float)
    debt_ebitda: Mapped[float | None] = mapped_column(Float)
    ffo_debt: Mapped[float | None] = mapped_column(Float)
    loan_value: Mapped[float | None] = mapped_column(Float)
    focf_debt: Mapped[float | None] = mapped_column(Float)
    liquidity: Mapped[float | None] = mapped_column(Float)

    snapshot: Mapped[FactCompanySnapshot] = relationship("FactCompanySnapshot", back_populates="credit_metrics")

    __table_args__ = (UniqueConstraint("snapshot_id", "metric_year", name="uq_metric_snapshot_year"),)


class DataLineage(Base):
    __tablename__ = "data_lineage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lineage_id: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str] = mapped_column(Text)
    target_ref: Mapped[str | None] = mapped_column(Text)
    stage_status: Mapped[str] = mapped_column(Text)
    upload_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("upload_audit.id"))
    snapshot_id: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    extra: Mapped[Any] = mapped_column("metadata", JSONB)

    upload: Mapped[UploadAudit | None] = relationship("UploadAudit", back_populates="lineage")


class PipelineState(Base):
    __tablename__ = "pipeline_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text, unique=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ)
    status: Mapped[str] = mapped_column(Text)
    files_found: Mapped[int | None] = mapped_column(Integer)
    files_processed: Mapped[int | None] = mapped_column(Integer)
    files_skipped: Mapped[int | None] = mapped_column(Integer)
    files_failed: Mapped[int | None] = mapped_column(Integer)
    total_duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    error_summary: Mapped[Any] = mapped_column(JSONB)
