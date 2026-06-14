from unittest.mock import patch

from api.pipeline.extractor import MasterSheetExtractor
from tests.fixtures.master_sheet_rows import A1_ROWS


class FakeWorksheet:
    def iter_rows(self, values_only=True):
        return iter(A1_ROWS)


class FakeWorkbook:
    sheetnames = ["MASTER"]

    def __getitem__(self, name):
        return FakeWorksheet()

    def close(self):
        pass


def test_bench_extract_rows(benchmark):
    extractor = MasterSheetExtractor()
    with (
        patch("api.pipeline.extractor.openpyxl.load_workbook", return_value=FakeWorkbook()),
        patch("api.pipeline.extractor.sha256_file", return_value="deadbeef"),
    ):
        benchmark(extractor.extract, "fake.xlsm")
