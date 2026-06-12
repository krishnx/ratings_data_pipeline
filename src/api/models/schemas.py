from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IndustrySegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    industry_name: str
    risk_score: str
    weight: float


class CreditMetricYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    ebitda_interest_cover: float | None
    debt_ebitda: float | None
    ffo_debt: float | None
    loan_value: float | None
    focf_debt: float | None
    liquidity: float | None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_name: str
    created_at: datetime


class CompanySnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    entity_name: str
    version_number: int
    valid_from: datetime
    valid_to: datetime | None
    corporate_sector: str | None
    reporting_currency: str | None
    country_of_origin: str | None
    accounting_principles: str | None
    business_year_end_month: str | None
    segmentation_criteria: str | None
    business_risk_profile: str | None
    blended_industry_risk_profile: str | None
    competitive_positioning: str | None
    market_share: str | None
    diversification: str | None
    operating_profitability: str | None
    sector_specific_factor_1: str | None
    sector_specific_factor_2: str | None
    financial_risk_profile: str | None
    leverage: str | None
    interest_cover: str | None
    cash_flow_cover: str | None
    liquidity_adjustment: str | None
    rating_methodologies: list[str]
    industry_segments: list[IndustrySegmentOut]
    credit_metrics: list[CreditMetricYearOut]


class CompanyListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    entity_name: str
    version_number: int
    valid_from: datetime
    corporate_sector: str | None
    reporting_currency: str | None
    country_of_origin: str | None
    business_risk_profile: str | None
    financial_risk_profile: str | None


class CompareOut(BaseModel):
    as_of_date: datetime
    companies: list[CompanySnapshotOut]


class SnapshotListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    entity_name: str
    version_number: int
    valid_from: datetime
    valid_to: datetime | None
    corporate_sector: str | None
    reporting_currency: str | None
    country_of_origin: str | None
    business_risk_profile: str | None
    financial_risk_profile: str | None


class SnapshotListOut(BaseModel):
    total_count: int
    items: list[SnapshotListItemOut]


class ValidationReportOut(BaseModel):
    passed: bool
    errors: list[dict]
    warnings: list[dict]
    completeness_pct: float
    validity_pct: float


class UploadListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    uploaded_at: datetime
    pipeline_run_id: str
    byte_size: int | None
    validation_status: str


class UploadDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    uploaded_at: datetime
    pipeline_run_id: str
    byte_size: int | None
    validation_status: str
    validation_report: dict | None


class UploadStatsOut(BaseModel):
    files_processed: int
    files_passed: int
    files_with_warnings: int
    files_failed: int
    by_sector: dict[str, int]
    by_currency: dict[str, int]
    by_country: dict[str, int]
