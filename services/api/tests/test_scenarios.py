"""Scenario engine tests: the run-rate identity, driver direction, sensitivity."""

from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from app.finance.scenarios import MODEL_NOTE, PRESETS, ScenarioEngine
from app.schemas import ScenarioAssumptions


def _summary(result, scenario_id: str):
    return next(summary for summary in result.scenarios if summary.scenario_id == scenario_id)


def test_zero_drivers_reproduce_the_trailing_twelve_months(engine, scenario_engine: ScenarioEngine) -> None:
    """The base case is the run-rate carried forward — this is the model contract."""
    result = scenario_engine.run(horizon_months=12)
    base_months = engine.trailing_twelve
    actual = engine.monthly_frame()
    # Tolerance: the projection recomputes quantity x price x fx from the values
    # stored in the CSV, which are rounded per row (2 dp money, 4 dp price,
    # 10 dp fx). The drift is well under one US dollar per month.
    tolerance = 1.5
    for index, month in enumerate(result.monthly["base"]):
        source_month = base_months[index]
        assert month.month == str(pd.Period(engine.as_of, freq="M") + index + 1)
        assert month.revenue_usd == pytest.approx(actual.loc[source_month, "revenue"], abs=tolerance)
        assert month.cogs_usd == pytest.approx(actual.loc[source_month, "cogs"], abs=tolerance)
        assert month.ebit_usd == pytest.approx(actual.loc[source_month, "ebit"], abs=tolerance)


def test_baseline_summary_equals_the_actual_trailing_year(engine, scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(horizon_months=12)
    frame = engine.monthly_frame()
    expected_revenue = float(frame.loc[engine.trailing_twelve, "revenue"].sum())
    assert result.baseline.revenue_usd == pytest.approx(expected_revenue, abs=1.0)
    assert result.baseline.revenue_delta_usd == 0.0
    assert result.base_period == f"{engine.trailing_twelve[0]}..{engine.trailing_twelve[-1]}"


def test_horizon_is_respected(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(horizon_months=6)
    assert result.horizon_months == 6
    assert all(len(months) == 6 for months in result.monthly.values())
    with pytest.raises(ValidationError):
        ScenarioAssumptions(horizon_months=0)
    with pytest.raises(ValidationError):
        ScenarioAssumptions(horizon_months=48)


def test_volume_growth_increases_revenue_and_ebit(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(assumptions=ScenarioAssumptions(volume_growth_pct=0.10))
    custom = _summary(result, "custom")
    base = result.baseline
    assert custom.revenue_usd > base.revenue_usd
    assert custom.ebit_usd > base.ebit_usd


def test_price_increase_flows_to_ebit(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(assumptions=ScenarioAssumptions(price_change_pct=0.05))
    custom = _summary(result, "custom")
    assert custom.ebit_usd > result.baseline.ebit_usd
    assert custom.gross_margin_pct > result.baseline.gross_margin_pct


def test_material_cost_increase_hurts_margin(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(assumptions=ScenarioAssumptions(material_cost_change_pct=0.08))
    custom = _summary(result, "custom")
    assert custom.ebit_usd < result.baseline.ebit_usd
    assert custom.gross_margin_pct < result.baseline.gross_margin_pct


def test_fx_depreciation_reduces_translated_revenue(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(assumptions=ScenarioAssumptions(fx_change_pct=-0.10))
    custom = _summary(result, "custom")
    assert custom.revenue_usd < result.baseline.revenue_usd


def test_rate_step_increases_interest_and_reduces_net_income(scenario_engine: ScenarioEngine) -> None:
    base = scenario_engine.run(horizon_months=12)
    hiked = scenario_engine.run(assumptions=ScenarioAssumptions(interest_rate_delta_pp=2.0))
    custom = _summary(hiked, "custom")
    assert custom.interest_expense_usd > base.baseline.interest_expense_usd
    assert custom.net_income_usd < base.baseline.net_income_usd


def test_dso_delta_delays_cash(scenario_engine: ScenarioEngine) -> None:
    base = scenario_engine.run(horizon_months=12)
    slower = scenario_engine.run(assumptions=ScenarioAssumptions(dso_days_delta=20))
    custom = _summary(slower, "custom")
    assert custom.operating_cash_flow_usd < base.baseline.operating_cash_flow_usd
    assert custom.ending_cash_usd < base.baseline.ending_cash_usd
    assert custom.ebit_usd == pytest.approx(base.baseline.ebit_usd, abs=1.0), "DSO must not change profit"


def test_opex_increase_reduces_ebit_but_not_gross_margin(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(assumptions=ScenarioAssumptions(opex_change_pct=0.10))
    custom = _summary(result, "custom")
    assert custom.ebit_usd < result.baseline.ebit_usd
    assert custom.gross_margin_pct == pytest.approx(result.baseline.gross_margin_pct, abs=1e-6)


def test_capex_change_affects_cash_not_ebit(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(assumptions=ScenarioAssumptions(capex_change_pct=0.50))
    custom = _summary(result, "custom")
    assert custom.ebit_usd == pytest.approx(result.baseline.ebit_usd, abs=1.0)
    assert custom.free_cash_flow_usd < result.baseline.free_cash_flow_usd


def test_downside_is_worse_than_base_everywhere(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(horizon_months=12)
    downside = _summary(result, "downside")
    upside = _summary(result, "upside")
    assert downside.ebit_usd < result.baseline.ebit_usd < upside.ebit_usd
    assert downside.ending_cash_usd < result.baseline.ending_cash_usd
    assert downside.ebit_delta_pct is not None and downside.ebit_delta_pct < 0
    assert upside.ebit_delta_pct is not None and upside.ebit_delta_pct > 0


def test_cost_and_fx_drivers_do_not_change_volume_driven_revenue(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(assumptions=ScenarioAssumptions(material_cost_change_pct=0.20))
    custom = _summary(result, "custom")
    # No price/volume/FX change, so revenue must be untouched: no hidden elasticity.
    assert custom.revenue_usd == pytest.approx(result.baseline.revenue_usd, abs=1.0)


def test_sensitivities_are_ranked_and_signed(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(horizon_months=12)
    assert result.sensitivities
    swings = [item.ebit_swing_usd for item in result.sensitivities]
    assert swings == sorted(swings, reverse=True)
    price = next(item for item in result.sensitivities if item.driver == "price_change_pct")
    assert price.ebit_impact_usd_high > 0 > price.ebit_impact_usd_low
    for item in result.sensitivities:
        assert item.ebit_swing_usd == pytest.approx(
            abs(item.ebit_impact_usd_high - item.ebit_impact_usd_low), abs=1e-6
        )


def test_sensitivity_can_be_disabled(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(horizon_months=6, include_sensitivity=False)
    assert result.sensitivities == []


def test_presets_are_documented_and_bounded(scenario_engine: ScenarioEngine) -> None:
    assert set(PRESETS) == {"base", "upside", "downside"}
    for definition in PRESETS.values():
        assert definition.description
        assert definition.assumptions.horizon_months >= 1
    result = scenario_engine.run(horizon_months=12)
    assert {summary.scenario_id for summary in result.scenarios} == {"base", "upside", "downside"}


def test_model_note_states_the_key_policy_choices(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(horizon_months=12)
    assert result.model_note == MODEL_NOTE
    for phrase in ("run-rate", "NOT the budget", "Debt is held flat", "taxes"):
        assert phrase.lower() in result.model_note.lower()


def test_scenario_runs_are_deterministic(scenario_engine: ScenarioEngine) -> None:
    first = scenario_engine.run(assumptions=ScenarioAssumptions(price_change_pct=0.03), horizon_months=12)
    second = scenario_engine.run(assumptions=ScenarioAssumptions(price_change_pct=0.03), horizon_months=12)
    assert first.model_dump() == second.model_dump()


def test_unknown_assumption_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioAssumptions.model_validate({"volume_growth_pct": 0.1, "make_it_up": 1})
    with pytest.raises(ValidationError):
        ScenarioAssumptions(volume_growth_pct=5.0)


def test_csv_export_covers_every_scenario_month(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(horizon_months=12)
    csv_text = scenario_engine.to_csv(result)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("scenario_id,month,revenue_usd")
    assert len(lines) == 1 + 12 * len(result.monthly)
    assert "custom" not in lines[1]


def test_region_subset_scenario(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(horizon_months=12, regions=["SG"])
    assert result.baseline.revenue_usd > 0
    assert result.baseline.revenue_usd < ScenarioEngine(scenario_engine.engine).run(horizon_months=12).baseline.revenue_usd


def test_custom_scenario_is_labelled_and_returned(scenario_engine: ScenarioEngine) -> None:
    result = scenario_engine.run(
        assumptions=ScenarioAssumptions(price_change_pct=0.02), scenario_id="custom", label="Pricing test"
    )
    custom = _summary(result, "custom")
    assert custom.label == "Pricing test"
    assert "custom" in result.assumptions
