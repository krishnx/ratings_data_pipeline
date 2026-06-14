"""
16 validation rules applied to a RawRecord.
Rules with ERROR severity block the file from loading.
Rules with WARNING severity load the file but annotate it.
"""

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from api.pipeline.constants import (
    KNOWN_ISO_CURRENCIES,
    NOTCH_PATTERN,
    PRESENCE_RULE_IDS,
    RATING_PATTERN,
    VALID_MONTHS,
)
from api.pipeline.extractor import RawRecord


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class RuleResult:
    rule_id: str
    severity: Severity
    field: str
    message: str
    observed_value: Any = None
    passed: bool = True


@dataclass
class ValidationReport:
    file: str
    passed: bool
    errors: list[RuleResult]
    warnings: list[RuleResult]
    completeness_pct: float
    validity_pct: float

    def to_dict(self) -> dict[str, Any]:
        def _fmt(r: RuleResult) -> dict[str, Any]:
            return {
                "rule_id": r.rule_id,
                "severity": r.severity.value,
                "field": r.field,
                "message": r.message,
                "observed_value": str(r.observed_value) if r.observed_value is not None else None,
            }

        return {
            "file": self.file,
            "passed": self.passed,
            "errors": [_fmt(r) for r in self.errors],
            "warnings": [_fmt(r) for r in self.warnings],
            "completeness_pct": self.completeness_pct,
            "validity_pct": self.validity_pct,
        }


RuleFn = Callable[[RawRecord], RuleResult]


def r01_entity_name_present(record: RawRecord) -> RuleResult:
    ok = bool(record.entity_name and record.entity_name.strip())
    return RuleResult(
        rule_id="R01",
        severity=Severity.ERROR,
        field="entity_name",
        passed=ok,
        message="OK" if ok else "entity_name is missing or blank",
        observed_value=record.entity_name,
    )


def r02_corporate_sector_present(record: RawRecord) -> RuleResult:
    ok = record.corporate_sector is not None
    return RuleResult(
        rule_id="R02",
        severity=Severity.ERROR,
        field="corporate_sector",
        passed=ok,
        message="OK" if ok else "corporate_sector is missing",
    )


def r03_reporting_currency_present(record: RawRecord) -> RuleResult:
    ok = record.reporting_currency is not None
    return RuleResult(
        rule_id="R03",
        severity=Severity.ERROR,
        field="reporting_currency",
        passed=ok,
        message="OK" if ok else "reporting_currency is missing",
    )


def r04_country_of_origin_present(record: RawRecord) -> RuleResult:
    ok = record.country_of_origin is not None
    return RuleResult(
        rule_id="R04",
        severity=Severity.ERROR,
        field="country_of_origin",
        passed=ok,
        message="OK" if ok else "country_of_origin is missing",
    )


def r05_industry_segments_non_empty(record: RawRecord) -> RuleResult:
    ok = len(record.industry_segments) > 0
    return RuleResult(
        rule_id="R05",
        severity=Severity.ERROR,
        field="industry_segments",
        passed=ok,
        message="OK" if ok else "industry_segments is empty",
        observed_value=len(record.industry_segments),
    )


def r06_segment_weights_are_floats(record: RawRecord) -> RuleResult:
    bad = []
    for seg in record.industry_segments:
        try:
            float(seg.weight)
        except (TypeError, ValueError):
            bad.append(seg.weight)
    ok = not bad
    return RuleResult(
        rule_id="R06",
        severity=Severity.ERROR,
        field="industry_segments.weight",
        passed=ok,
        message="OK" if ok else f"Non-float weights: {bad}",
        observed_value=bad or None,
    )


def r07_metric_years_valid(record: RawRecord) -> RuleResult:
    bad = [m.year for m in record.credit_metrics if not (1900 <= m.year <= 2100)]
    ok = not bad
    return RuleResult(
        rule_id="R07",
        severity=Severity.ERROR,
        field="credit_metrics.year",
        passed=ok,
        message="OK" if ok else f"Years out of [1900, 2100]: {bad}",
        observed_value=bad or None,
    )


def r08_metric_values_finite(record: RawRecord) -> RuleResult:
    bad = []
    for m in record.credit_metrics:
        for attr in ("ebitda_interest_cover", "debt_ebitda", "ffo_debt", "loan_value", "focf_debt", "liquidity"):
            v = getattr(m, attr)
            if v is not None and not math.isfinite(v):
                bad.append(f"year={m.year}/{attr}={v}")
    ok = not bad
    return RuleResult(
        rule_id="R08",
        severity=Severity.ERROR,
        field="credit_metrics",
        passed=ok,
        message="OK" if ok else f"Non-finite metric values: {bad}",
        observed_value=bad or None,
    )


def r09_business_year_end_month_valid(record: RawRecord) -> RuleResult:
    v = record.business_year_end_month
    ok = v is None or v.lower() in VALID_MONTHS
    return RuleResult(
        rule_id="R09",
        severity=Severity.ERROR,
        field="business_year_end_month",
        passed=ok,
        message="OK" if ok else f"'{v}' is not a valid month name",
        observed_value=v,
    )


def r10_weights_sum_to_one(record: RawRecord) -> RuleResult:
    if not record.industry_segments:
        return RuleResult(
            rule_id="R10",
            severity=Severity.ERROR,
            field="industry_segments.weight",
            passed=True,
            message="No segments to check",
        )
    total = sum(seg.weight for seg in record.industry_segments)
    ok = abs(total - 1.0) <= 0.01
    return RuleResult(
        rule_id="R10",
        severity=Severity.ERROR,
        field="industry_segments.weight",
        passed=ok,
        message="OK" if ok else f"Weights sum to {total:.6f}, expected 1.0 ± 0.01",
        observed_value=round(total, 6),
    )


def r11_each_weight_in_range(record: RawRecord) -> RuleResult:
    bad = [seg.weight for seg in record.industry_segments if not (0.0 < seg.weight <= 1.0)]
    ok = not bad
    return RuleResult(
        rule_id="R11",
        severity=Severity.ERROR,
        field="industry_segments.weight",
        passed=ok,
        message="OK" if ok else f"Weights not in (0, 1]: {bad}",
        observed_value=bad or None,
    )


def r12_currency_is_known_iso(record: RawRecord) -> RuleResult:
    v = record.reporting_currency
    ok = v is None or v.upper() in KNOWN_ISO_CURRENCIES
    return RuleResult(
        rule_id="R12",
        severity=Severity.WARNING,
        field="reporting_currency",
        passed=ok,
        message="OK" if ok else f"'{v}' is not a known ISO 4217 code",
        observed_value=v,
    )


def r13_risk_scores_match_pattern(record: RawRecord) -> RuleResult:
    scores = [
        record.business_risk_profile,
        record.blended_industry_risk_profile,
        record.financial_risk_profile,
        *[seg.risk_score for seg in record.industry_segments],
    ]
    bad = [s for s in scores if s is not None and not RATING_PATTERN.match(s)]
    ok = not bad
    return RuleResult(
        rule_id="R13",
        severity=Severity.WARNING,
        field="risk_scores",
        passed=ok,
        message="OK" if ok else f"Scores not matching credit rating pattern: {bad}",
        observed_value=bad or None,
    )


def r14_liquidity_adjustment_format(record: RawRecord) -> RuleResult:
    v = record.liquidity_adjustment
    ok = v is None or bool(NOTCH_PATTERN.match(v.strip()))
    return RuleResult(
        rule_id="R14",
        severity=Severity.WARNING,
        field="liquidity_adjustment",
        passed=ok,
        message="OK" if ok else f"'{v}' does not match '+N notch(es)' pattern",
        observed_value=v,
    )


def r15_credit_metrics_span_multiple_years(record: RawRecord) -> RuleResult:
    years = [m.year for m in record.credit_metrics]
    ok = len(years) >= 2
    return RuleResult(
        rule_id="R15",
        severity=Severity.WARNING,
        field="credit_metrics",
        passed=ok,
        message="OK" if ok else f"Only {len(years)} year(s) of metrics; time-series limited",
        observed_value=years,
    )


def r16_company_name_not_only_special(record: RawRecord) -> RuleResult:
    v = record.entity_name or ""
    ok = bool(re.search(r"[a-zA-Z]", v))
    return RuleResult(
        rule_id="R16",
        severity=Severity.WARNING,
        field="entity_name",
        passed=ok,
        message="OK" if ok else f"Entity name '{v}' contains no letters",
        observed_value=v,
    )


RULE_REGISTRY: list[RuleFn] = [
    r01_entity_name_present,
    r02_corporate_sector_present,
    r03_reporting_currency_present,
    r04_country_of_origin_present,
    r05_industry_segments_non_empty,
    r06_segment_weights_are_floats,
    r07_metric_years_valid,
    r08_metric_values_finite,
    r09_business_year_end_month_valid,
    r10_weights_sum_to_one,
    r11_each_weight_in_range,
    r12_currency_is_known_iso,
    r13_risk_scores_match_pattern,
    r14_liquidity_adjustment_format,
    r15_credit_metrics_span_multiple_years,
    r16_company_name_not_only_special,
]


def validate(record: RawRecord, registry: list[RuleFn] = RULE_REGISTRY) -> ValidationReport:
    results = [rule(record) for rule in registry]
    errors = [r for r in results if not r.passed and r.severity == Severity.ERROR]
    warnings = [r for r in results if not r.passed and r.severity == Severity.WARNING]

    total = len(results)
    passed_count = sum(1 for r in results if r.passed)

    presence = [r for r in results if r.rule_id in PRESENCE_RULE_IDS]
    completeness_pct = (sum(1 for r in presence if r.passed) / len(presence) * 100.0) if presence else 100.0
    validity_pct = (passed_count / total * 100.0) if total else 100.0

    return ValidationReport(
        file=record.source_file,
        passed=not errors,
        errors=errors,
        warnings=warnings,
        completeness_pct=round(completeness_pct, 2),
        validity_pct=round(validity_pct, 2),
    )
