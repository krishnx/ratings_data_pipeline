"""
Unit tests for the 16-rule validation framework.
All tests are pure Python — no I/O.
"""
from api.pipeline.extractor import CreditMetricYear, IndustrySegment, RawRecord
from api.pipeline.validator import (
    RULE_REGISTRY,
    Severity,
    validate,
    r01_entity_name_present,
    r05_industry_segments_non_empty,
    r07_metric_years_valid,
    r08_metric_values_finite,
    r12_currency_is_known_iso,
    r13_risk_scores_match_pattern,
    r14_liquidity_adjustment_format,
    r15_credit_metrics_span_multiple_years,
)
from datetime import datetime, timezone


def _make_record(**kwargs) -> RawRecord:
    defaults = {
        "source_file": "test.xlsm",
        "file_sha256": "abc",
        "extracted_at": datetime.now(timezone.utc),
        "entity_name": "Test Corp",
        "corporate_sector": "Financials",
        "rating_methodologies": ["General"],
        "industry_segments": [IndustrySegment(0, "Consumer", "BBB", 1.0)],
        "segmentation_criteria": "EBITDA contribution",
        "reporting_currency": "EUR",
        "country_of_origin": "Germany",
        "accounting_principles": "IFRS",
        "business_year_end_month": "December",
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
            CreditMetricYear(2020, 12.0, 1.8, 18.0, None, 9.0, 1.2),
        ],
    }
    defaults.update(kwargs)
    return RawRecord(**defaults)


def test_R01_missing_entity_name():
    r = r01_entity_name_present(_make_record(entity_name=None))
    assert not r.passed
    assert r.severity == Severity.ERROR


def test_R01_blank_entity_name():
    r = r01_entity_name_present(_make_record(entity_name="   "))
    assert not r.passed


def test_R01_valid_entity_name():
    r = r01_entity_name_present(_make_record(entity_name="Company A"))
    assert r.passed


def test_R05_empty_segments():
    r = r05_industry_segments_non_empty(_make_record(industry_segments=[]))
    assert not r.passed
    assert r.severity == Severity.ERROR


def test_R10_weights_sum_valid():
    segs = [IndustrySegment(0, "A", "BBB", 0.15), IndustrySegment(1, "B", "BB", 0.85)]
    record = _make_record(industry_segments=segs)
    from api.pipeline.validator import r10_weights_sum_to_one
    r = r10_weights_sum_to_one(record)
    assert r.passed


def test_R10_weights_sum_invalid():
    segs = [IndustrySegment(0, "A", "BBB", 0.15), IndustrySegment(1, "B", "BB", 0.70)]
    record = _make_record(industry_segments=segs)
    from api.pipeline.validator import r10_weights_sum_to_one
    r = r10_weights_sum_to_one(record)
    assert not r.passed
    assert r.severity == Severity.ERROR


def test_R10_weight_tolerance():
    segs = [IndustrySegment(0, "A", "BBB", 0.999)]
    record = _make_record(industry_segments=segs)
    from api.pipeline.validator import r10_weights_sum_to_one
    r = r10_weights_sum_to_one(record)
    assert r.passed  # within ±0.01


def test_R11_zero_weight():
    segs = [IndustrySegment(0, "A", "BBB", 0.0)]
    from api.pipeline.validator import r11_each_weight_in_range
    r = r11_each_weight_in_range(_make_record(industry_segments=segs))
    assert not r.passed


def test_R11_over_one_weight():
    segs = [IndustrySegment(0, "A", "BBB", 1.1)]
    from api.pipeline.validator import r11_each_weight_in_range
    r = r11_each_weight_in_range(_make_record(industry_segments=segs))
    assert not r.passed


def test_R07_invalid_year():
    metrics = [CreditMetricYear(1800, None, None, None, None, None, None)]
    r = r07_metric_years_valid(_make_record(credit_metrics=metrics))
    assert not r.passed
    assert r.severity == Severity.ERROR


def test_R08_nan_metric():
    import math
    metrics = [CreditMetricYear(2020, math.nan, None, None, None, None, None)]
    r = r08_metric_values_finite(_make_record(credit_metrics=metrics))
    assert not r.passed


def test_R12_unknown_currency():
    r = r12_currency_is_known_iso(_make_record(reporting_currency="XYZ"))
    assert not r.passed
    assert r.severity == Severity.WARNING


def test_R12_known_currency_passes():
    r = r12_currency_is_known_iso(_make_record(reporting_currency="EUR"))
    assert r.passed


def test_R13_valid_rating():
    segs = [IndustrySegment(0, "A", "BBB+", 1.0)]
    record = _make_record(industry_segments=segs, business_risk_profile="BBB+",
                          blended_industry_risk_profile="BBB", financial_risk_profile="BB+")
    r = r13_risk_scores_match_pattern(record)
    assert r.passed


def test_R13_invalid_rating():
    segs = [IndustrySegment(0, "A", "XXXX", 1.0)]
    record = _make_record(industry_segments=segs)
    r = r13_risk_scores_match_pattern(record)
    assert not r.passed
    assert r.severity == Severity.WARNING


def test_R14_valid_notch():
    r = r14_liquidity_adjustment_format(_make_record(liquidity_adjustment="+1 notch"))
    assert r.passed


def test_R14_invalid_notch():
    r = r14_liquidity_adjustment_format(_make_record(liquidity_adjustment="more liquidity"))
    assert not r.passed
    assert r.severity == Severity.WARNING


def test_R15_only_one_year():
    metrics = [CreditMetricYear(2020, None, None, None, None, None, None)]
    r = r15_credit_metrics_span_multiple_years(_make_record(credit_metrics=metrics))
    assert not r.passed
    assert r.severity == Severity.WARNING


def test_completeness_pct():
    record = _make_record(
        entity_name=None,
        corporate_sector=None,
        reporting_currency="EUR",
        country_of_origin="Germany",
        industry_segments=[IndustrySegment(0, "A", "BBB", 1.0)],
    )
    report = validate(record)
    assert report.completeness_pct == 60.0  # 3 of 5 presence rules pass


def test_valid_record_passes_all_error_rules():
    report = validate(_make_record())
    assert report.passed
    assert len(report.errors) == 0


def test_rule_registry_has_16_rules():
    assert len(RULE_REGISTRY) == 16
