"""Unit tests for the numeric helpers — the undefined-value contract."""

from __future__ import annotations

import math

import pytest

from app.finance.formulas import (
    annualise,
    days_in_month,
    days_in_months,
    month_span,
    pct_change,
    previous_month,
    safe_div,
    same_month_previous_year,
    sum_available,
)


def test_days_in_month_handles_leap_year() -> None:
    assert days_in_month("2024-02") == 29
    assert days_in_month("2023-02") == 28
    assert days_in_month("2024-12") == 31
    assert days_in_months(["2024-01", "2024-02"]) == 60


def test_safe_div_returns_value_for_normal_inputs() -> None:
    result = safe_div(10.0, 4.0)
    assert result.status == "ok"
    assert result.value == pytest.approx(2.5)


def test_safe_div_refuses_zero_denominator() -> None:
    result = safe_div(10.0, 0.0, label="revenue")
    assert result.value is None
    assert result.status == "undefined"
    assert "zero" in (result.note or "")


def test_safe_div_reports_missing_inputs_distinctly() -> None:
    numerator = safe_div(None, 4.0)
    assert numerator.status == "missing"
    assert "numerator" in (numerator.note or "")

    denominator = safe_div(4.0, None, label="cogs")
    assert denominator.status == "missing"
    assert "cogs" in (denominator.note or "")

    nan_input = safe_div(float("nan"), 4.0)
    assert nan_input.value is None
    assert nan_input.status == "missing"


def test_pct_change_undefined_for_zero_base() -> None:
    assert pct_change(10.0, 0.0).status == "undefined"
    assert pct_change(10.0, 0.0).value is None
    ok = pct_change(110.0, 100.0)
    assert ok.status == "ok"
    assert ok.value == pytest.approx(0.1)
    # A negative base uses its absolute value so the sign of the change stays readable.
    assert pct_change(-90.0, -100.0).value == pytest.approx(0.1)


def test_pct_change_missing_input() -> None:
    assert pct_change(None, 100.0).status == "missing"
    assert pct_change(100.0, None).status == "missing"


def test_sum_available_counts_missing_cells() -> None:
    total, missing = sum_available([1.0, None, 2.0, float("nan"), 3.5])
    assert total == pytest.approx(6.5)
    assert missing == 2
    total, missing = sum_available([])
    assert total == 0.0
    assert missing == 0


def test_annualise_scales_flow() -> None:
    assert annualise(100.0, 3) == pytest.approx(400.0)
    assert annualise(100.0, 12) == pytest.approx(100.0)
    assert annualise(None, 3) is None
    assert annualise(100.0, 0) is None


def test_month_navigation() -> None:
    assert previous_month("2024-01") == "2023-12"
    assert previous_month("2024-12") == "2024-11"
    assert same_month_previous_year("2024-03") == "2023-03"
    months = [f"2024-{index:02d}" for index in range(1, 13)]
    assert month_span("2024-03", "2024-05", months) == ["2024-03", "2024-04", "2024-05"]
    assert month_span("2025-01", "2025-02", months) == []


def test_no_helper_ever_returns_nan() -> None:
    """A NaN must never escape: it becomes None with a status."""
    for result in (safe_div(float("nan"), 1.0), pct_change(float("nan"), 1.0)):
        assert result.value is None
        assert not (isinstance(result.value, float) and math.isnan(result.value))
