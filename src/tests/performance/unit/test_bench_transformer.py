from datetime import datetime, timezone

from api.pipeline.extractor import CreditMetricYear, IndustrySegment, RawRecord
from api.pipeline.transformer import transform


def _make_record() -> RawRecord:
    return RawRecord(
        source_file="test.xlsm",
        file_sha256="abc",
        extracted_at=datetime.now(timezone.utc),
        entity_name="  Company A  ",
        corporate_sector="Consumer",
        rating_methodologies=["General"],
        industry_segments=[IndustrySegment(0, " Consumer ", "BBB", 1)],
        segmentation_criteria="EBITDA",
        reporting_currency="EUR",
        country_of_origin="Germany",
        accounting_principles="IFRS",
        business_year_end_month="december",
        business_risk_profile="BBB",
        blended_industry_risk_profile="BBB",
        competitive_positioning="BBB",
        market_share="BBB",
        diversification="BBB",
        operating_profitability="BBB",
        sector_specific_factor_1="BBB",
        sector_specific_factor_2=None,
        financial_risk_profile="BBB",
        leverage="BBB",
        interest_cover="BBB",
        cash_flow_cover="BBB",
        liquidity_adjustment="+1 notch",
        credit_metrics=[
            CreditMetricYear(2019, 10.0, 2.0, 15.0, None, 8.0, 1.0),
        ],
    )


def test_bench_transform_record(benchmark):
    record = _make_record()
    benchmark(transform, record)
