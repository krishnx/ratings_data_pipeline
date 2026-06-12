from sqlalchemy import (
    ARRAY,
    BigInteger,
    Column,
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
from sqlalchemy.orm import DeclarativeBase, relationship

# Timezone-aware timestamp (maps to TIMESTAMPTZ in PostgreSQL)
TIMESTAMPTZ = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class DimCompany(Base):
    __tablename__ = "dim_company"

    id = Column(Integer, primary_key=True)
    entity_name = Column(Text, nullable=False, unique=True)
    created_at = Column(TIMESTAMPTZ, nullable=False)

    snapshots = relationship("FactCompanySnapshot", back_populates="company")


class UploadAudit(Base):
    __tablename__ = "upload_audit"

    id = Column(Integer, primary_key=True)
    filename = Column(Text, nullable=False)
    file_sha256 = Column(Text, nullable=False, unique=True)
    uploaded_at = Column(TIMESTAMPTZ, nullable=False)
    pipeline_run_id = Column(Text, nullable=False)
    byte_size = Column(BigInteger)
    validation_status = Column(Text, nullable=False)
    validation_report = Column(JSONB)

    file_store = relationship("UploadFileStore", back_populates="upload", uselist=False)
    snapshots = relationship("FactCompanySnapshot", back_populates="upload")
    lineage = relationship("DataLineage", back_populates="upload")


class UploadFileStore(Base):
    __tablename__ = "upload_file_store"

    upload_id = Column(Integer, ForeignKey("upload_audit.id", ondelete="CASCADE"), primary_key=True)
    raw_bytes = Column(LargeBinary, nullable=False)

    upload = relationship("UploadAudit", back_populates="file_store")


class FactCompanySnapshot(Base):
    __tablename__ = "fact_company_snapshot"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("dim_company.id"), nullable=False)
    upload_id = Column(Integer, ForeignKey("upload_audit.id"), nullable=False)
    version_number = Column(Integer, nullable=False)

    valid_from = Column(TIMESTAMPTZ, nullable=False)
    valid_to = Column(TIMESTAMPTZ)

    corporate_sector = Column(Text)
    reporting_currency = Column(Text)
    country_of_origin = Column(Text)
    accounting_principles = Column(Text)
    business_year_end_month = Column(Text)
    segmentation_criteria = Column(Text)

    business_risk_profile = Column(Text)
    blended_industry_risk_profile = Column(Text)
    competitive_positioning = Column(Text)
    market_share = Column(Text)
    diversification = Column(Text)
    operating_profitability = Column(Text)
    sector_specific_factor_1 = Column(Text)
    sector_specific_factor_2 = Column(Text)
    financial_risk_profile = Column(Text)
    leverage = Column(Text)
    interest_cover = Column(Text)
    cash_flow_cover = Column(Text)
    liquidity_adjustment = Column(Text)

    rating_methodologies = Column(ARRAY(Text))
    raw_extras = Column(JSONB)
    search_vector = Column(
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

    company = relationship("DimCompany", back_populates="snapshots")
    upload = relationship("UploadAudit", back_populates="snapshots")
    industry_segments = relationship(
        "FactIndustrySegment",
        back_populates="snapshot",
        order_by="FactIndustrySegment.segment_index",
        cascade="all, delete-orphan",
    )
    credit_metrics = relationship(
        "FactCreditMetric",
        back_populates="snapshot",
        order_by="FactCreditMetric.metric_year",
        cascade="all, delete-orphan",
    )


class FactIndustrySegment(Base):
    __tablename__ = "fact_industry_segment"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("fact_company_snapshot.id", ondelete="CASCADE"), nullable=False)
    segment_index = Column(SmallInteger, nullable=False)
    industry_name = Column(Text, nullable=False)
    risk_score = Column(Text, nullable=False)
    weight = Column(Numeric(6, 4), nullable=False)

    snapshot = relationship("FactCompanySnapshot", back_populates="industry_segments")

    __table_args__ = (UniqueConstraint("snapshot_id", "segment_index", name="uq_segment_snapshot_idx"),)


class FactCreditMetric(Base):
    __tablename__ = "fact_credit_metric"

    id = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("fact_company_snapshot.id", ondelete="CASCADE"), nullable=False)
    metric_year = Column(SmallInteger, nullable=False)
    ebitda_interest_cover = Column(Float)
    debt_ebitda = Column(Float)
    ffo_debt = Column(Float)
    loan_value = Column(Float)
    focf_debt = Column(Float)
    liquidity = Column(Float)

    snapshot = relationship("FactCompanySnapshot", back_populates="credit_metrics")

    __table_args__ = (UniqueConstraint("snapshot_id", "metric_year", name="uq_metric_snapshot_year"),)


class DataLineage(Base):
    __tablename__ = "data_lineage"

    id = Column(Integer, primary_key=True)
    lineage_id = Column(Text, nullable=False)
    stage = Column(Text, nullable=False)
    source_ref = Column(Text, nullable=False)
    target_ref = Column(Text)
    stage_status = Column(Text, nullable=False)
    upload_id = Column(Integer, ForeignKey("upload_audit.id"))
    snapshot_id = Column(Integer)
    occurred_at = Column(TIMESTAMPTZ, nullable=False)
    extra = Column("metadata", JSONB)  # 'metadata' is reserved by SQLAlchemy DeclarativeBase

    upload = relationship("UploadAudit", back_populates="lineage")


class PipelineState(Base):
    __tablename__ = "pipeline_state"

    id = Column(Integer, primary_key=True)
    run_id = Column(Text, nullable=False, unique=True)
    started_at = Column(TIMESTAMPTZ, nullable=False)
    finished_at = Column(TIMESTAMPTZ)
    status = Column(Text, nullable=False)
    files_found = Column(Integer)
    files_processed = Column(Integer)
    files_skipped = Column(Integer)
    files_failed = Column(Integer)
    total_duration_ms = Column(BigInteger)
    error_summary = Column(JSONB)
