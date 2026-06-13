"""
Transform a RawRecord into a clean DomainRecord ready for loading.
No DB access, no validation logic — only data normalization.
"""
from dataclasses import dataclass

from api.pipeline.constants import VALID_MONTHS
from api.pipeline.extractor import CreditMetricYear, IndustrySegment, RawRecord


@dataclass
class DomainSegment:
    index: int
    industry_name: str
    risk_score: str
    weight: float


@dataclass
class DomainMetricYear:
    year: int
    ebitda_interest_cover: float | None
    debt_ebitda: float | None
    ffo_debt: float | None
    loan_value: float | None
    focf_debt: float | None
    liquidity: float | None


@dataclass
class DomainRecord:
    entity_name: str
    corporate_sector: str | None
    rating_methodologies: list[str]
    industry_segments: list[DomainSegment]
    segmentation_criteria: str | None
    reporting_currency: str | None
    country_of_origin: str | None
    accounting_principles: str | None
    business_year_end_month: str | None
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
    credit_metrics: list[DomainMetricYear]


def _normalize_month(v: str | None) -> str | None:
    if v is None:
        return None
    norm = v.strip().lower()
    return v.strip().title() if norm in VALID_MONTHS else v.strip()


def _normalize_str(v: str | None) -> str | None:
    return v.strip() if v else None


def _transform_segment(seg: IndustrySegment) -> DomainSegment:
    return DomainSegment(
        index=seg.index,
        industry_name=seg.industry_name.strip(),
        risk_score=seg.risk_score.strip(),
        weight=float(seg.weight),
    )


def _transform_metric(m: CreditMetricYear) -> DomainMetricYear:
    return DomainMetricYear(
        year=m.year,
        ebitda_interest_cover=m.ebitda_interest_cover,
        debt_ebitda=m.debt_ebitda,
        ffo_debt=m.ffo_debt,
        loan_value=m.loan_value,
        focf_debt=m.focf_debt,
        liquidity=m.liquidity,
    )


def transform(record: RawRecord) -> DomainRecord:
    return DomainRecord(
        entity_name=(record.entity_name or "").strip(),
        corporate_sector=_normalize_str(record.corporate_sector),
        rating_methodologies=[m.strip() for m in record.rating_methodologies],
        industry_segments=[_transform_segment(s) for s in record.industry_segments],
        segmentation_criteria=_normalize_str(record.segmentation_criteria),
        reporting_currency=_normalize_str(record.reporting_currency),
        country_of_origin=_normalize_str(record.country_of_origin),
        accounting_principles=_normalize_str(record.accounting_principles),
        business_year_end_month=_normalize_month(record.business_year_end_month),
        business_risk_profile=_normalize_str(record.business_risk_profile),
        blended_industry_risk_profile=_normalize_str(record.blended_industry_risk_profile),
        competitive_positioning=_normalize_str(record.competitive_positioning),
        market_share=_normalize_str(record.market_share),
        diversification=_normalize_str(record.diversification),
        operating_profitability=_normalize_str(record.operating_profitability),
        sector_specific_factor_1=_normalize_str(record.sector_specific_factor_1),
        sector_specific_factor_2=_normalize_str(record.sector_specific_factor_2),
        financial_risk_profile=_normalize_str(record.financial_risk_profile),
        leverage=_normalize_str(record.leverage),
        interest_cover=_normalize_str(record.interest_cover),
        cash_flow_cover=_normalize_str(record.cash_flow_cover),
        liquidity_adjustment=_normalize_str(record.liquidity_adjustment),
        credit_metrics=[_transform_metric(m) for m in record.credit_metrics],
    )
