"""Risk register tests: rules fire, thresholds bind, gaps are declared."""

from __future__ import annotations

import pytest

from app.finance.engine import FinancialEngine
from app.finance.risk import SEVERITY_SCORE, RiskEngine, Thresholds
from tests.helpers import build_long_macro, build_tiny_dataset, with_macro


def _signal_ids(register) -> set[str]:
    return {signal.signal_id for signal in register.signals}


def test_seed_dataset_produces_a_credible_register(risk_engine: RiskEngine) -> None:
    register = risk_engine.build()
    assert register.overall_level in {"high", "critical"}
    assert register.score > 0
    ids = _signal_ids(register)
    # The demo is engineered to contain these specific problems.
    for expected in {"RC-01", "RC-05", "RC-06", "RC-08", "RC-11"}:
        assert expected in ids, f"{expected} should fire on the demo dataset"
    assert len(register.data_gaps) >= 3


def test_high_severity_signals_come_first(risk_engine: RiskEngine) -> None:
    register = risk_engine.build()
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    ranks = [order[signal.severity] for signal in register.signals]
    assert ranks == sorted(ranks)


def test_score_is_the_weighted_sum_of_severities(risk_engine: RiskEngine) -> None:
    register = risk_engine.build()
    expected = min(100.0, sum(SEVERITY_SCORE[signal.severity] for signal in register.signals))
    assert register.score == pytest.approx(round(expected, 1))


def test_every_signal_is_auditable(risk_engine: RiskEngine) -> None:
    register = risk_engine.build()
    for signal in register.signals:
        assert signal.detail
        assert signal.recommended_check
        # Most rules report on the latest month; the budget rules report year-to-date.
        assert signal.period.startswith(register.period[:4])
        assert signal.source_ids
        assert signal.synthetic is True
        assert signal.observed_value is not None
        if signal.threshold is not None:
            assert signal.threshold_unit
        for item in signal.supporting:
            assert item.unit
            assert item.label


def test_healthy_company_does_not_raise_coverage_or_margin_signals(static_thresholds: Thresholds) -> None:
    dataset = with_macro(build_tiny_dataset(), build_long_macro())
    engine = FinancialEngine(dataset)
    register = RiskEngine(engine, thresholds=static_thresholds).build(month="2024-03")
    ids = _signal_ids(register)
    # Coverage is 5.00x on the tiny dataset and the margin is flat: no signal.
    assert "RC-01" not in ids
    assert "RC-03" not in ids
    assert "RC-05" not in ids
    assert "RC-06" not in ids


def test_boundary_between_medium_and_high_coverage() -> None:
    dataset = with_macro(build_tiny_dataset(), build_long_macro())
    frame = dataset.financials.copy()
    # EBIT 75, interest 15 -> 5.00x. Raise interest to 40 -> 1.875x (< 2.0 floor, > 1.5).
    frame["interest_expense_usd"] = 40.0
    patched = dataset.__class__(
        financials=frame, budget=dataset.budget, macro=dataset.macro, profile=dataset.profile, manifest=dataset.manifest
    )
    register = RiskEngine(FinancialEngine(patched)).build(month="2024-03")
    coverage = next(signal for signal in register.signals if signal.signal_id == "RC-01")
    assert coverage.severity == "high"
    assert coverage.observed_value == pytest.approx(75.0 / 40.0, abs=1e-4)


def test_below_1_5x_coverage_is_critical() -> None:
    dataset = with_macro(build_tiny_dataset(), build_long_macro())
    frame = dataset.financials.copy()
    frame["interest_expense_usd"] = 60.0  # 1.25x
    patched = dataset.__class__(
        financials=frame, budget=dataset.budget, macro=dataset.macro, profile=dataset.profile, manifest=dataset.manifest
    )
    register = RiskEngine(FinancialEngine(patched)).build(month="2024-03")
    coverage = next(signal for signal in register.signals if signal.signal_id == "RC-01")
    assert coverage.severity == "critical"
    assert register.overall_level in {"high", "critical"}


def test_custom_thresholds_are_respected() -> None:
    dataset = with_macro(build_tiny_dataset(), build_long_macro())
    engine = FinancialEngine(dataset)
    relaxed = RiskEngine(engine, thresholds=Thresholds(interest_coverage_min=1.0)).build(month="2024-03")
    assert "RC-01" not in _signal_ids(relaxed)


def test_declared_gap_raises_a_data_quality_signal() -> None:
    dataset = with_macro(
        build_tiny_dataset(overrides={"2024-03": {"inventory_usd": None}}), build_long_macro()
    )
    register = RiskEngine(FinancialEngine(dataset)).build(month="2024-03")
    quality = next(signal for signal in register.signals if signal.signal_id == "RC-13")
    assert quality.category == "data_quality"
    assert quality.observed_value == pytest.approx(1.0)


def test_zero_revenue_month_does_not_crash_the_register() -> None:
    dataset = with_macro(
        build_tiny_dataset(overrides={"2024-03": {"revenue_usd": 0.0, "unit_price_local": 0.0}}),
        build_long_macro(),
    )
    register = RiskEngine(FinancialEngine(dataset)).build(month="2024-03")
    assert register.overall_level in {"low", "medium", "high", "critical"}
    assert any("could not be computed" in gap or "unavailable" in gap for gap in register.data_gaps)


def test_market_rule_uses_the_fixture_series() -> None:
    dataset = with_macro(build_tiny_dataset(), build_long_macro(months=24))
    register = RiskEngine(FinancialEngine(dataset)).build(month="2024-03")
    market = [signal for signal in register.signals if signal.signal_id == "RC-14"]
    assert market, "the funding-cost rule should fire when 13+ months of the rate series exist"
    assert "DEMO fixtures" in market[0].detail
    assert market[0].source_ids and market[0].source_ids[0].startswith("market:DFF@")


def test_register_without_enough_history_reports_gaps() -> None:
    dataset = with_macro(build_tiny_dataset(months=("2024-01",)), build_long_macro())
    register = RiskEngine(FinancialEngine(dataset)).build(month="2024-01")
    joined = " ".join(register.data_gaps)
    assert "12 months of history" in joined
    assert "runway" in joined.lower()


def test_region_subset_scoping(risk_engine: RiskEngine) -> None:
    register = risk_engine.build(regions=["SG"])
    assert register.period == risk_engine.engine.as_of
    assert all(signal.period for signal in register.signals)


def test_unknown_month_raises(risk_engine: RiskEngine) -> None:
    with pytest.raises(KeyError):
        risk_engine.build(month="2019-01")
