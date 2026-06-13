"""
Unit tests for the transformer module.
"""

from datetime import datetime, timezone

from api.pipeline.extractor import CreditMetricYear, IndustrySegment, RawRecord
from api.pipeline.transformer import transform


def _make_raw(**kwargs) -> RawRecord:
    defaults = {
        "source_file": "test.xlsm",
        "file_sha256": "abc",
        "extracted_at": datetime.now(timezone.utc),
        "entity_name": "  Company A  ",
        "corporate_sector": "Consumer Goods",
        "rating_methodologies": ["General"],
        "industry_segments": [IndustrySegment(0, " Consumer ", "BBB", 1)],
        "segmentation_criteria": "EBITDA contribution",
        "reporting_currency": "EUR",
        "country_of_origin": "Germany",
        "accounting_principles": "IFRS",
        "business_year_end_month": "december",
        "business_risk_profile": "BBB",
        "blended_industry_risk_profile": "BBB",
        "competitive_positioning": "BBB",
        "market_share": "BBB",
        "diversification": "BBB",
        "operating_profitability": "BBB",
        "sector_specific_factor_1": "BBB",
        "sector_specific_factor_2": None,
        "financial_risk_profile": "BBB",
        "leverage": "BBB",
        "interest_cover": "BBB",
        "cash_flow_cover": "BBB",
        "liquidity_adjustment": "+1 notch",
        "credit_metrics": [
            CreditMetricYear(2019, 10.0, 2.0, 15.0, None, 8.0, 1.0),
        ],
    }
    defaults.update(kwargs)
    return RawRecord(**defaults)


def test_entity_name_stripped():
    domain = transform(_make_raw(entity_name="  Company A  "))
    assert domain.entity_name == "Company A"


def test_month_title_case():
    domain = transform(_make_raw(business_year_end_month="december"))
    assert domain.business_year_end_month == "December"


def test_industry_name_stripped():
    domain = transform(_make_raw(industry_segments=[IndustrySegment(0, " Consumer ", "BBB", 1)]))
    assert domain.industry_segments[0].industry_name == "Consumer"


def test_credit_metric_none_passthrough():
    raw = _make_raw(credit_metrics=[CreditMetricYear(2020, None, None, None, None, None, None)])
    domain = transform(raw)
    m = domain.credit_metrics[0]
    assert m.ebitda_interest_cover is None
    assert m.ffo_debt is None


def test_weight_coercion_from_int():
    domain = transform(_make_raw(industry_segments=[IndustrySegment(0, "A", "BBB", 1)]))
    assert isinstance(domain.industry_segments[0].weight, float)
    assert domain.industry_segments[0].weight == 1.0


def test_unknown_month_kept_as_is():
    domain = transform(_make_raw(business_year_end_month="FY_END"))
    assert domain.business_year_end_month == "FY_END"
