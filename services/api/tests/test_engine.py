"""Financial engine tests.

Two layers:

* ``tiny_engine`` — a hand-built three-month dataset where every expectation is a
  literal number derived on paper, so the formulas are pinned independently of
  the generator.
* ``engine`` — the shipped 24-month demo dataset, used for identity checks
  (relationships that must hold for every month) rather than for literals.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.finance.engine import FinancialEngine
from tests.helpers import build_tiny_dataset, with_macro, build_long_macro


# ----------------------------------------------------------------------
# tiny dataset: known values
# ----------------------------------------------------------------------
def test_period_metrics_match_hand_calculated_values(tiny_engine: FinancialEngine) -> None:
    pack = tiny_engine.metrics(months=["2024-01", "2024-02", "2024-03"])
    values = pack.values
    assert pack.period == "2024-01..2024-03"
    assert values["revenue"].value == pytest.approx(1500.0)
    assert values["cogs"].value == pytest.approx(900.0)
    assert values["gross_profit"].value == pytest.approx(600.0)
    assert values["gross_margin"].value == pytest.approx(0.40)
    assert values["opex"].value == pytest.approx(300.0)
    assert values["ebitda"].value == pytest.approx(300.0)
    assert values["depreciation_amortization"].value == pytest.approx(75.0)
    assert values["ebit"].value == pytest.approx(225.0)
    assert values["operating_margin"].value == pytest.approx(0.15)
    assert values["interest_expense"].value == pytest.approx(45.0)
    assert values["ebt"].value == pytest.approx(180.0)
    assert values["cash_taxes"].value == pytest.approx(39.6)
    assert values["net_income"].value == pytest.approx(140.4)
    assert values["operating_cash_flow"].value == pytest.approx(180.0)
    assert values["capex"].value == pytest.approx(120.0)
    assert values["free_cash_flow"].value == pytest.approx(60.0)
    assert values["interest_coverage"].value == pytest.approx(5.0)


def test_ebit_is_not_ebitda(tiny_engine: FinancialEngine) -> None:
    pack = tiny_engine.metrics(months=["2024-01"])
    assert pack.values["ebitda"].value == pytest.approx(100.0)
    assert pack.values["ebit"].value == pytest.approx(75.0)
    assert "ebitda - depreciation" in pack.values["ebit"].formula


def test_stock_metrics_use_the_closing_balance_not_the_sum(tiny_engine: FinancialEngine) -> None:
    """Regression: cash/debt are point-in-time balances, never summed over months."""
    pack = tiny_engine.metrics(months=["2024-01", "2024-02", "2024-03"])
    assert pack.values["cash"].value == pytest.approx(1000.0)  # not 3000
    assert pack.values["debt"].value == pytest.approx(500.0)  # not 1500
    assert pack.values["net_debt"].value == pytest.approx(-500.0)
    assert "point-in-time" in pack.values["cash"].formula
    single = tiny_engine.metrics(months=["2024-03"])
    assert single.values["cash"].value == pytest.approx(pack.values["cash"].value)


def test_working_capital_days_follow_the_documented_formula(tiny_engine: FinancialEngine) -> None:
    pack = tiny_engine.metrics(months=["2024-01", "2024-02", "2024-03"])
    # days = 31 + 29 + 31 = 91 for Jan-Mar 2024
    days = 91.0
    revenue_per_day = 1500.0 / days
    cogs_per_day = 900.0 / days
    assert pack.values["dso_days_ending"].value == pytest.approx(250.0 / revenue_per_day, abs=1e-3)
    assert pack.values["dso_days"].value == pytest.approx(250.0 / revenue_per_day, abs=1e-3)
    assert pack.values["dio_days"].value == pytest.approx(150.0 / cogs_per_day, abs=1e-3)
    assert pack.values["dpo_days"].value == pytest.approx(100.0 / cogs_per_day, abs=1e-3)
    assert pack.values["cash_conversion_cycle_days"].value == pytest.approx(
        pack.values["dso_days"].value + pack.values["dio_days"].value - pack.values["dpo_days"].value, abs=1e-3
    )
    assert "no opening balance" in (pack.values["dso_days"].note or "")


def test_average_receivables_uses_opening_and_closing(tiny_dataset) -> None:
    dataset = with_macro(build_tiny_dataset(), build_long_macro())
    frame = dataset.financials.copy()
    frame.loc[frame["month"] == "2024-03", "accounts_receivable_usd"] = 550.0
    patched = dataset.__class__(
        financials=frame, budget=dataset.budget, macro=dataset.macro, profile=dataset.profile, manifest=dataset.manifest
    )
    engine = FinancialEngine(patched)
    pack = engine.metrics(months=["2024-02", "2024-03"])
    days = 29.0 + 31.0
    revenue_per_day = 1000.0 / days
    # opening AR = 2024-01 closing = 250, closing AR = 550 -> average 400
    assert pack.values["dso_days"].value == pytest.approx(400.0 / revenue_per_day, rel=1e-6)
    assert pack.values["dso_days_ending"].value == pytest.approx(550.0 / revenue_per_day, rel=1e-6)


def test_current_ratio_uses_closing_balances(tiny_engine: FinancialEngine) -> None:
    pack = tiny_engine.metrics(months=["2024-03"])
    # (cash 1000 + AR 250 + inventory 150) / (AP 100 + short-term debt 100)
    assert pack.values["current_ratio"].value == pytest.approx(1400.0 / 200.0)


def test_net_leverage_annualises_ebitda(tiny_engine: FinancialEngine) -> None:
    pack = tiny_engine.metrics(months=["2024-01", "2024-02", "2024-03"])
    ebitda = 300.0
    annualised = ebitda * 12 / 3
    assert pack.values["net_leverage"].value == pytest.approx(-500.0 / annualised, abs=1e-3)


def test_month_on_month_and_year_on_year(tiny_dataset) -> None:
    months = tuple(f"2024-{index:02d}" for index in range(1, 13)) + ("2025-01",)
    dataset = with_macro(build_tiny_dataset(months=months), build_long_macro())
    engine = FinancialEngine(dataset)
    pack = engine.metrics(months=["2025-01"])
    assert pack.values["revenue_mom"].value == pytest.approx(0.0)
    assert pack.values["revenue_yoy"].value == pytest.approx(0.0)


def test_zero_denominator_is_undefined_not_zero(tiny_dataset) -> None:
    dataset = with_macro(
        build_tiny_dataset(overrides={"2024-02": {"unit_price_local": 0.0, "revenue_usd": 0.0}}),
        build_long_macro(),
    )
    engine = FinancialEngine(dataset)
    pack = engine.metrics(months=["2024-02"])
    assert pack.values["revenue"].value == pytest.approx(0.0)
    for metric_id in ("gross_margin", "operating_margin", "dso_days", "net_margin"):
        cited = pack.values[metric_id]
        assert cited.value is None, metric_id
        assert cited.status == "undefined", metric_id
        assert "zero" in (cited.note or "")


def test_missing_input_is_reported_as_missing(tiny_dataset) -> None:
    dataset = with_macro(
        build_tiny_dataset(overrides={"2024-02": {"inventory_usd": None}}), build_long_macro()
    )
    engine = FinancialEngine(dataset)
    pack = engine.metrics(months=["2024-02"])
    assert pack.values["dio_days"].status == "missing"
    assert pack.values["dio_days"].value is None
    assert pack.values["cash_conversion_cycle_days"].status == "missing"


def test_monthly_series_and_budget_variance(tiny_engine: FinancialEngine) -> None:
    series = tiny_engine.series(months=list(tiny_engine.months))
    assert len(series.points) == 3
    point = series.points[0]
    assert point.revenue_usd == pytest.approx(500.0)
    assert point.ebit_usd == pytest.approx(75.0)
    assert point.budget_revenue_usd == pytest.approx(600.0)
    assert point.revenue_variance_usd == pytest.approx(-100.0)
    assert point.revenue_variance_pct == pytest.approx(-100.0 / 600.0, abs=1e-5)

    variance = tiny_engine.budget_variance(months=list(tiny_engine.months))
    assert variance.values["revenue_variance"].value == pytest.approx(1500.0 - 1800.0)
    assert variance.values["revenue_variance_pct"].value == pytest.approx(-300.0 / 1800.0, abs=1e-5)
    # budget EBIT = 3 x (600 - 360 - 120 - 25) = 285
    assert variance.values["ebit_variance"].value == pytest.approx(225.0 - 285.0)
    assert variance.values["ebit_variance_pct"].value == pytest.approx((225.0 - 285.0) / 285.0, abs=1e-5)
    assert variance.values["ebit_variance_pct"].basis == "variance"


def test_budget_variance_is_missing_when_no_plan_exists(tiny_dataset) -> None:
    empty_budget = tiny_dataset.budget.iloc[0:0]
    patched = tiny_dataset.__class__(
        financials=tiny_dataset.financials,
        budget=empty_budget,
        macro=tiny_dataset.macro,
        profile=tiny_dataset.profile,
        manifest=tiny_dataset.manifest,
    )
    engine = FinancialEngine(patched)
    variance = engine.budget_variance(months=["2024-01"])
    cited = variance.values["revenue_variance"]
    assert cited.value is None
    assert cited.status == "missing"
    assert "No budget layer" in (cited.note or "")


def test_unknown_month_raises(tiny_engine: FinancialEngine) -> None:
    with pytest.raises(ValueError):
        tiny_engine.metrics(months=["2020-01"])


def test_region_filter_changes_the_result(tiny_dataset) -> None:
    frame = tiny_dataset.financials.copy()
    second = frame.copy()
    second["region"] = "TH"
    second["currency"] = "THB"
    second["revenue_usd"] = second["revenue_usd"] * 2
    combined = dataset = tiny_dataset.__class__(
        financials=pd.concat([frame, second], ignore_index=True),
        budget=tiny_dataset.budget,
        macro=tiny_dataset.macro,
        profile=tiny_dataset.profile,
        manifest=tiny_dataset.manifest,
    )
    engine = FinancialEngine(combined)
    all_regions = engine.metrics(months=["2024-01"])
    th_only = engine.metrics(months=["2024-01"], regions=["TH"])
    assert all_regions.values["revenue"].value == pytest.approx(1500.0)
    assert th_only.values["revenue"].value == pytest.approx(1000.0)
    assert set(engine.revenue_by_currency(["2024-01"])) == {"SGD", "THB"}


# ----------------------------------------------------------------------
# shipped demo dataset: identities that must hold for every month
# ----------------------------------------------------------------------
def test_monthly_frame_identities_hold_for_the_demo_data(engine: FinancialEngine) -> None:
    frame = engine.monthly_frame()
    assert len(frame) == 24
    assert (frame["gross_profit"] - (frame["revenue"] - frame["cogs"])).abs().max() < 1e-6
    assert (frame["ebitda"] - (frame["gross_profit"] - frame["opex"])).abs().max() < 1e-6
    assert (frame["ebit"] - (frame["ebitda"] - frame["dep_amort"])).abs().max() < 1e-6
    assert (frame["net_income"] - (frame["ebit"] - frame["interest_expense"] - frame["cash_taxes"])).abs().max() < 1e-6
    assert (frame["free_cash_flow"] - (frame["operating_cash_flow"] - frame["capex"])).abs().max() < 1e-6


def test_demo_data_margin_and_leverage_story(engine: FinancialEngine) -> None:
    frame = engine.monthly_frame()
    assert frame["gross_margin"].iloc[-1] < frame["gross_margin"].iloc[0]
    assert frame["dso_days"].iloc[-1] > frame["dso_days"].iloc[0]
    assert frame["cash"].iloc[-1] < frame["cash"].iloc[0]


def test_full_period_metrics_are_internally_consistent(engine: FinancialEngine) -> None:
    pack = engine.metrics(months=engine.months)
    values = pack.values
    assert values["gross_profit"].value == pytest.approx(values["revenue"].value - values["cogs"].value)
    assert values["gross_margin"].value == pytest.approx(values["gross_profit"].value / values["revenue"].value, rel=1e-4)
    assert values["ebit"].value == pytest.approx(values["ebitda"].value - values["depreciation_amortization"].value)
    assert values["interest_coverage"].value == pytest.approx(values["ebit"].value / values["interest_expense"].value, rel=1e-4)
    assert values["free_cash_flow"].value == pytest.approx(
        values["operating_cash_flow"].value - values["capex"].value
    )
    # Two years of cash is a closing balance, never a sum of two years of flows.
    assert values["cash"].value < values["revenue"].value


def test_partial_coverage_is_flagged_not_hidden(engine: FinancialEngine) -> None:
    pack = engine.metrics(months=["2024-07"])
    assert "partial coverage" in (pack.values["revenue"].note or "")
    assert pack.values["revenue"].status == "ok"


def test_series_flags_the_declared_gap(engine: FinancialEngine) -> None:
    series = engine.series(months=engine.months)
    assert len(series.points) == 24
    assert all(point.revenue_usd is not None for point in series.points)


def test_lineage_is_synthetic_and_explains_the_gap(engine: FinancialEngine) -> None:
    lineage = engine.lineage()
    assert len(lineage) == 3
    assert all(item.synthetic for item in lineage)
    assert any("2024-07" in note for item in lineage for note in item.notes)
    assert all(item.rows > 0 for item in lineage)


def test_every_metric_carries_unit_period_formula_and_sources(engine: FinancialEngine) -> None:
    pack = engine.metrics(months=[engine.as_of])
    assert pack.values
    for metric_id, cited in pack.values.items():
        assert cited.metric_id == metric_id
        assert cited.unit, metric_id
        assert cited.period == engine.as_of, metric_id
        assert cited.formula, metric_id
        assert cited.source_ids, metric_id
        assert cited.synthetic is True
