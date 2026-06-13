"""
Unit tests for MasterSheetExtractor using in-memory row fixtures.
No I/O beyond reading real .xlsm files in integration tests.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from api.pipeline.exceptions import MissingSheetError
from api.pipeline.extractor import MasterSheetExtractor, _normalize, _is_int_year
from api.pipeline.protocols import SheetReader
from tests.fixtures.master_sheet_rows import A1_ROWS, B1_ROWS

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
A1_FILE = DATA_DIR / "corporates_A_1.xlsm"
B1_FILE = DATA_DIR / "corporates_B_1.xlsm"

REAL_FILES_AVAILABLE = A1_FILE.exists()


class FakeSheetReader:
    """Test double for SheetReader — returns canned rows without touching the filesystem."""

    def __init__(self, rows: list[tuple], has_sheet: bool = True) -> None:
        self._rows = rows
        self._has_sheet = has_sheet

    def read_rows(self, path, sheet_name: str) -> list[tuple]:
        if not self._has_sheet:
            raise MissingSheetError(f"No '{sheet_name}' sheet")
        return self._rows


def _make_extractor_with_rows(rows):
    extractor = MasterSheetExtractor(reader=FakeSheetReader(rows))
    with patch("api.pipeline.extractor.sha256_file", return_value="deadbeef"):
        return extractor.extract("fake.xlsm")


def test_extract_company_a1_entity_name():
    record = _make_extractor_with_rows(A1_ROWS)
    assert record.entity_name == "Company A"


def test_extract_company_a1_single_segment():
    record = _make_extractor_with_rows(A1_ROWS)
    assert len(record.industry_segments) == 1
    seg = record.industry_segments[0]
    assert seg.industry_name == "Consumer Products: Non-Discretionary"
    assert seg.risk_score == "A"
    assert seg.weight == 1.0


def test_extract_company_b1_multi_segment():
    record = _make_extractor_with_rows(B1_ROWS)
    assert len(record.industry_segments) == 2
    assert record.industry_segments[0].weight == 0.15
    assert record.industry_segments[1].weight == 0.85


def test_extract_company_b1_entity_name():
    record = _make_extractor_with_rows(B1_ROWS)
    assert record.entity_name == "Company B"


def test_multi_methodology():
    record = _make_extractor_with_rows(A1_ROWS)
    assert len(record.rating_methodologies) == 2
    assert "General Corporate Rating Methodology" in record.rating_methodologies


def test_single_methodology():
    record = _make_extractor_with_rows(B1_ROWS)
    assert len(record.rating_methodologies) == 1


def test_credit_metrics_only_integer_years():
    record = _make_extractor_with_rows(A1_ROWS)
    years = [m.year for m in record.credit_metrics]
    assert all(isinstance(y, int) for y in years)
    assert 2018 in years
    assert 2019 in years
    assert 2020 in years
    # Estimated years should be excluded
    for y in years:
        assert y < 2025


def test_liquidity_label_disambiguation():
    record = _make_extractor_with_rows(A1_ROWS)
    # Row 30 → liquidity_adjustment (string)
    assert record.liquidity_adjustment == "-2 notches"
    # Row 41 → credit metric (float, accessible via credit_metrics)
    liquidity_metrics = [m.liquidity for m in record.credit_metrics]
    assert any(v is not None for v in liquidity_metrics)


def test_empty_rows_stripped():
    # All None rows should not contribute to label_map
    record = _make_extractor_with_rows(A1_ROWS)
    assert record.entity_name is not None  # sanity: data still extracted


def test_optional_field_none():
    record = _make_extractor_with_rows(A1_ROWS)
    assert record.sector_specific_factor_2 is None


def test_missing_master_sheet():
    extractor = MasterSheetExtractor(reader=FakeSheetReader(A1_ROWS, has_sheet=False))
    with patch("api.pipeline.extractor.sha256_file", return_value="deadbeef"):
        with pytest.raises(MissingSheetError):
            extractor.extract("no_master.xlsm")


def test_label_normalization():
    assert _normalize("  CorporateSector  ") == "corporatesector"
    assert _normalize("Rated entity") == "rated entity"


def test_weight_as_int():
    record = _make_extractor_with_rows(A1_ROWS)
    assert isinstance(record.industry_segments[0].weight, float)
    assert record.industry_segments[0].weight == 1.0


def test_is_int_year():
    assert _is_int_year(2024) is True
    assert _is_int_year(2024.0) is True
    assert _is_int_year("2025E") is False
    assert _is_int_year("Locked") is False


@pytest.mark.skipif(not REAL_FILES_AVAILABLE, reason="Data files not present")
def test_real_file_a1():
    extractor = MasterSheetExtractor()
    record = extractor.extract(A1_FILE)
    assert record.entity_name == "Company A"
    assert record.reporting_currency == "EUR"
    assert len(record.industry_segments) == 1
    assert len(record.credit_metrics) >= 2


@pytest.mark.skipif(not REAL_FILES_AVAILABLE, reason="Data files not present")
def test_real_file_b1_multi_segment():
    extractor = MasterSheetExtractor()
    record = extractor.extract(B1_FILE)
    assert record.entity_name == "Company B"
    assert len(record.industry_segments) == 2
    total_weight = sum(s.weight for s in record.industry_segments)
    assert abs(total_weight - 1.0) < 0.01
