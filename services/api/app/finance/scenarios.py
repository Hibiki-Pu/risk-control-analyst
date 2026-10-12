"""Driver-based what-if engine (deterministic, auditable, no LLM).

Model contract
--------------
Baseline
    The trailing twelve months of actuals are used as the run-rate. Each future
    month takes the *same calendar month* of that window, so seasonality is
    preserved. ``base`` (all drivers at zero) therefore means "this year repeats
    itself" — it is a run-rate, NOT the management plan. The plan is compared
    separately in the budget-variance module.

Drivers
    ``volume_growth_pct``  applied to quantity, compounded monthly from an
                           annual rate: ``(1+g)^(i/12)``.
    ``price_change_pct``   applied to local selling price, effective month 1.
    ``material_cost_change_pct``  applied to the **USD** cost per unit
                           (materials are imported and invoiced in USD).
    ``labor_cost_change_pct`` / ``overhead_cost_change_pct``  applied to the
                           **local-currency** cost per unit, so they are also
                           translated at the scenario FX rate.
    ``opex_change_pct``    applied to operating expenses, which are treated as
                           fixed within the horizon (they do NOT scale with
                           volume — a deliberate, stated policy).
    ``interest_rate_delta_pp``  added to the closing annual rate; debt is held
                           flat (no new financing, no amortisation).
    ``fx_change_pct``      change in USD per unit of local currency.
    ``dso_days_delta``     added to the closing DSO (ending-receivables basis).

Excluded by design: new debt, equity raises, dividends, M&A, tax-rate changes,
and any second-order elasticity (price changes do not move volume).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import pandas as pd

from app.finance.engine import TAX_RATE_USED, FinancialEngine
from app.finance.formulas import safe_div
from app.schemas import (
    ScenarioAssumptions,
    ScenarioDefinition,
    ScenarioMonth,
    ScenarioResult,
    ScenarioSummary,
    SensitivityItem,
)

MODEL_NOTE = (
    "Baseline = trailing twelve months run-rate repeated by calendar month (seasonality preserved), "
    "NOT the budget. Materials are priced in USD, labour and overhead in local currency. "
    "Operating expenses are treated as fixed within the horizon. Debt is held flat with no new "
    "financing or amortisation. Taxes accrue at 22% of positive pre-tax profit. Working-capital days "
    "are held at the closing level plus any user-specified delta."
)

#: Tornado shocks: (field, label, shock size in the field's own unit).
SENSITIVITY_SHOCKS: tuple[tuple[str, str, float], ...] = (
    ("volume_growth_pct", "Volume growth", 0.02),
    ("price_change_pct", "Selling price", 0.01),
    ("material_cost_change_pct", "Material cost", 0.02),
    ("labor_cost_change_pct", "Labour cost", 0.01),
    ("overhead_cost_change_pct", "Production overhead", 0.01),
    ("opex_change_pct", "Operating expenses", 0.01),
    ("interest_rate_delta_pp", "Interest rate (pp)", 1.0),
    ("fx_change_pct", "FX (USD per local currency)", 0.02),
    ("dso_days_delta", "DSO (days)", 5.0),
)

PRESETS: dict[str, ScenarioDefinition] = {
    "base": ScenarioDefinition(
        scenario_id="base",
        label="Base (run-rate)",
        description="Trailing twelve months repeated with every driver unchanged.",
        assumptions=ScenarioAssumptions(),
    ),
    "upside": ScenarioDefinition(
        scenario_id="upside",
        label="Upside (price + mix recovery)",
        description=(
            "Volume +4pp, price +1.5%, input costs -3pp, one rate cut of 0.5pp, "
            "local currencies recover 2% and opex is held 1% lower."
        ),
        assumptions=ScenarioAssumptions(
            volume_growth_pct=0.04,
            price_change_pct=0.015,
            material_cost_change_pct=-0.03,
            labor_cost_change_pct=-0.01,
            overhead_cost_change_pct=-0.01,
            opex_change_pct=-0.01,
            interest_rate_delta_pp=-0.5,
            fx_change_pct=0.02,
        ),
    ),
    "downside": ScenarioDefinition(
        scenario_id="downside",
        label="Downside (cost + rate + FX squeeze)",
        description=(
            "Volume -6pp, price -2%, material +6pp, wages +3pp, overhead +3pp, "
            "rates +1.5pp, local currencies weaken 4% and collection slips 15 days."
        ),
        assumptions=ScenarioAssumptions(
            volume_growth_pct=-0.06,
            price_change_pct=-0.02,
            material_cost_change_pct=0.06,
            labor_cost_change_pct=0.03,
            overhead_cost_change_pct=0.03,
            opex_change_pct=0.02,
            interest_rate_delta_pp=1.5,
            fx_change_pct=-0.04,
            dso_days_delta=15,
        ),
    ),
}


@dataclass
class BaselineInputs:
    """Extracted run-rate drivers, all keyed by calendar month (1-12)."""

    base_months: list[str]
    regions: list[str]
    quantity: dict[tuple[str, int], float] = field(default_factory=dict)
    price_local: dict[tuple[str, int], float] = field(default_factory=dict)
    fx: dict[tuple[str, int], float] = field(default_factory=dict)
    material_unit_usd: dict[tuple[str, int], float] = field(default_factory=dict)
    labor_unit_local: dict[tuple[str, int], float] = field(default_factory=dict)
    overhead_unit_local: dict[tuple[str, int], float] = field(default_factory=dict)
    opex_usd: dict[int, float] = field(default_factory=dict)
    dep_amort_usd: dict[int, float] = field(default_factory=dict)
    capex_usd: float = 0.0
    opening_ar: float = 0.0
    opening_cash: float = 0.0
    debt: float = 0.0
    rate_pct: float = 0.0
    dso_days: float = 0.0
    dio_days: float = 0.0
    dpo_days: float = 0.0
    tax_rate: float = TAX_RATE_USED

    def as_dict(self) -> dict:
        return {
            "base_months": self.base_months,
            "regions": self.regions,
            "capex_usd_monthly": round(self.capex_usd, 2),
            "opening_ar": round(self.opening_ar, 2),
            "opening_cash": round(self.opening_cash, 2),
            "debt": round(self.debt, 2),
            "rate_pct": self.rate_pct,
            "dso_days": round(self.dso_days, 2),
            "dio_days": round(self.dio_days, 2),
            "dpo_days": round(self.dpo_days, 2),
            "tax_rate": self.tax_rate,
        }


def _calendar_month(month: str) -> int:
    return int(month.split("-")[1])


def _shift_month(month: str, offset: int) -> str:
    period = pd.Period(month, freq="M") + offset
    return str(period)


class ScenarioEngine:
    def __init__(self, engine: FinancialEngine):
        self.engine = engine

    # ------------------------------------------------------------------
    def baseline(self, regions: Sequence[str] | None = None) -> BaselineInputs:
        window = self.engine.trailing_twelve
        frame = self.engine.scope(regions, window).copy()
        monthly = self.engine.monthly_frame(regions)
        last = self.engine.as_of

        inputs = BaselineInputs(
            base_months=window,
            regions=sorted(frame["region"].unique().tolist()),
        )
        for _, row in frame.iterrows():
            key = (row["region"], _calendar_month(row["month"]))
            quantity = float(row["quantity"])
            fx = float(row["fx_rate_to_usd"])
            inputs.quantity[key] = quantity
            inputs.price_local[key] = float(row["unit_price_local"])
            inputs.fx[key] = fx
            inputs.material_unit_usd[key] = float(row["cogs_material_usd"]) / quantity if quantity else 0.0
            local_denominator = quantity * fx
            inputs.labor_unit_local[key] = float(row["cogs_labor_usd"]) / local_denominator if local_denominator else 0.0
            inputs.overhead_unit_local[key] = (
                float(row["cogs_overhead_usd"]) / local_denominator if local_denominator else 0.0
            )

        for month in window:
            month_of_year = _calendar_month(month)
            inputs.opex_usd[month_of_year] = float(monthly.loc[month, "opex"])
            inputs.dep_amort_usd[month_of_year] = float(monthly.loc[month, "dep_amort"])

        inputs.capex_usd = float(monthly.loc[window, "capex"].mean())
        inputs.opening_ar = float(monthly.loc[last, "accounts_receivable"])
        inputs.opening_cash = float(monthly.loc[last, "cash"])
        inputs.debt = float(monthly.loc[last, "debt"])
        inputs.rate_pct = float(self.engine.actuals.loc[self.engine.actuals["month"] == last, "annual_interest_rate_pct"].mean())
        inputs.dso_days = float(monthly.loc[last, "dso_days_ending"])
        inputs.dio_days = float(monthly.loc[last, "dio_days"])
        inputs.dpo_days = float(monthly.loc[last, "dpo_days"])
        return inputs

    # ------------------------------------------------------------------
    def project(self, inputs: BaselineInputs, assumptions: ScenarioAssumptions) -> list[ScenarioMonth]:
        """Run one scenario. Pure function of (inputs, assumptions)."""
        months: list[ScenarioMonth] = []
        ar_previous = inputs.opening_ar
        inventory_previous = None
        ap_previous = None
        cash = inputs.opening_cash
        rate = inputs.rate_pct + assumptions.interest_rate_delta_pp
        dso_days = inputs.dso_days + assumptions.dso_days_delta

        for step in range(1, assumptions.horizon_months + 1):
            month = _shift_month(self.engine.as_of, step)
            month_of_year = _calendar_month(month)
            volume_factor = (1.0 + assumptions.volume_growth_pct) ** (step / 12.0)
            material_factor = (1.0 + assumptions.material_cost_change_pct) ** (step / 12.0)
            labor_factor = (1.0 + assumptions.labor_cost_change_pct) ** (step / 12.0)
            overhead_factor = (1.0 + assumptions.overhead_cost_change_pct) ** (step / 12.0)
            fx_factor = (1.0 + assumptions.fx_change_pct) ** (step / 12.0)

            revenue = material = labor = overhead = 0.0
            for region in inputs.regions:
                key = (region, month_of_year)
                if key not in inputs.quantity:
                    continue
                quantity = inputs.quantity[key] * volume_factor
                price_local = inputs.price_local[key] * (1.0 + assumptions.price_change_pct)
                fx = inputs.fx[key] * fx_factor
                revenue += quantity * price_local * fx
                material += quantity * inputs.material_unit_usd[key] * material_factor
                labor += quantity * inputs.labor_unit_local[key] * fx * labor_factor
                overhead += quantity * inputs.overhead_unit_local[key] * fx * overhead_factor

            cogs = material + labor + overhead
            gross_profit = revenue - cogs
            opex = inputs.opex_usd.get(month_of_year, 0.0) * (1.0 + assumptions.opex_change_pct) ** (step / 12.0)
            dep_amort = inputs.dep_amort_usd.get(month_of_year, 0.0)
            ebit = gross_profit - opex - dep_amort
            ebitda = gross_profit - opex
            interest = inputs.debt * rate / 100.0 / 12.0
            pretax = ebit - interest
            taxes = max(pretax, 0.0) * inputs.tax_rate
            net_income = pretax - taxes

            receivables = revenue * dso_days / 30.0
            inventory = cogs * inputs.dio_days / 30.0
            payables = cogs * inputs.dpo_days / 30.0
            if inventory_previous is None:
                # First projection month: only receivables have an opening
                # balance in this model, so the opening NWC step is the AR move.
                change_in_nwc = receivables - ar_previous
            else:
                change_in_nwc = (receivables + inventory - payables) - (
                    ar_previous + inventory_previous - ap_previous
                )

            ocf = ebit + dep_amort - taxes - change_in_nwc
            capex = inputs.capex_usd * (1.0 + assumptions.capex_change_pct)
            fcf = ocf - capex
            cash = cash + fcf

            months.append(
                ScenarioMonth(
                    month=month,
                    revenue_usd=round(revenue, 2),
                    cogs_usd=round(cogs, 2),
                    gross_profit_usd=round(gross_profit, 2),
                    gross_margin_pct=round(gross_profit / revenue, 6) if revenue else None,
                    ebit_usd=round(ebit, 2),
                    operating_margin_pct=round(ebit / revenue, 6) if revenue else None,
                    interest_expense_usd=round(interest, 2),
                    net_income_usd=round(net_income, 2),
                    operating_cash_flow_usd=round(ocf, 2),
                    free_cash_flow_usd=round(fcf, 2),
                    cash_usd=round(cash, 2),
                    dso_days=round(dso_days, 2),
                )
            )
            ar_previous, inventory_previous, ap_previous = receivables, inventory, payables

        return months

    # ------------------------------------------------------------------
    def _summarise(
        self,
        scenario_id: str,
        label: str,
        months: list[ScenarioMonth],
        baseline: ScenarioSummary | None = None,
    ) -> ScenarioSummary:
        revenue = sum(month.revenue_usd for month in months)
        gross_profit = sum(month.gross_profit_usd for month in months)
        ebit = sum(month.ebit_usd for month in months)
        interest = sum(month.interest_expense_usd for month in months)
        net_income = sum(month.net_income_usd for month in months)
        ocf = sum(month.operating_cash_flow_usd for month in months)
        fcf = sum(month.free_cash_flow_usd for month in months)
        cash_values = [month.cash_usd for month in months]
        monthly_net = [month.free_cash_flow_usd for month in months]
        average_burn = -sum(monthly_net) / len(monthly_net) if monthly_net else 0.0
        runway = safe_div(cash_values[-1], average_burn if average_burn > 0 else None, label="monthly net burn")

        summary = ScenarioSummary(
            scenario_id=scenario_id,
            label=label,
            horizon_months=len(months),
            revenue_usd=round(revenue, 2),
            gross_profit_usd=round(gross_profit, 2),
            gross_margin_pct=round(gross_profit / revenue, 6) if revenue else None,
            ebit_usd=round(ebit, 2),
            operating_margin_pct=round(ebit / revenue, 6) if revenue else None,
            interest_expense_usd=round(interest, 2),
            net_income_usd=round(net_income, 2),
            operating_cash_flow_usd=round(ocf, 2),
            free_cash_flow_usd=round(fcf, 2),
            ending_cash_usd=round(cash_values[-1], 2),
            minimum_cash_usd=round(min(cash_values), 2),
            cash_runway_months=None if runway.value is None else round(runway.value, 2),
            months_with_negative_cash=sum(1 for value in cash_values if value < 0),
        )
        if baseline is not None:
            summary.revenue_delta_usd = round(summary.revenue_usd - baseline.revenue_usd, 2)
            summary.ebit_delta_usd = round(summary.ebit_usd - baseline.ebit_usd, 2)
            summary.ebit_delta_pct = (
                round((summary.ebit_usd - baseline.ebit_usd) / abs(baseline.ebit_usd), 6)
                if baseline.ebit_usd
                else None
            )
            summary.fcf_delta_usd = round(summary.free_cash_flow_usd - baseline.free_cash_flow_usd, 2)
        return summary

    # ------------------------------------------------------------------
    def run(
        self,
        assumptions: ScenarioAssumptions | None = None,
        scenario_id: str = "custom",
        label: str = "Custom scenario",
        include_presets: bool = True,
        regions: Sequence[str] | None = None,
        include_sensitivity: bool = True,
        horizon_months: int | None = None,
    ) -> ScenarioResult:
        inputs = self.baseline(regions)
        definitions: dict[str, ScenarioAssumptions] = {}

        if include_presets:
            for key, definition in PRESETS.items():
                resolved_horizon = (
                    horizon_months
                    if horizon_months is not None
                    else (assumptions or definition.assumptions).horizon_months
                )
                definitions[key] = definition.assumptions.model_copy(
                    update={"horizon_months": resolved_horizon}
                )
        if assumptions is not None:
            definitions[scenario_id] = assumptions

        horizon = next(iter(definitions.values())).horizon_months if definitions else 12
        monthly: dict[str, list[ScenarioMonth]] = {}
        for key, scenario_assumptions in definitions.items():
            monthly[key] = self.project(inputs, scenario_assumptions)

        base_key = "base" if "base" in monthly else next(iter(monthly))
        baseline_summary = self._summarise(base_key, "Base (run-rate)", monthly[base_key])
        summaries = [baseline_summary]
        for key, months in monthly.items():
            if key == base_key:
                continue
            label_lookup = PRESETS[key].label if key in PRESETS else label
            summaries.append(self._summarise(key, label_lookup, months, baseline_summary))

        sensitivities: list[SensitivityItem] = []
        if include_sensitivity:
            base_assumptions = definitions.get("base", ScenarioAssumptions(horizon_months=horizon))
            base_ebit = baseline_summary.ebit_usd
            for field_name, label, shock in SENSITIVITY_SHOCKS:
                low_assumptions = base_assumptions.model_copy(
                    update={field_name: getattr(base_assumptions, field_name) - shock}
                )
                high_assumptions = base_assumptions.model_copy(
                    update={field_name: getattr(base_assumptions, field_name) + shock}
                )
                low_ebit = sum(month.ebit_usd for month in self.project(inputs, low_assumptions))
                high_ebit = sum(month.ebit_usd for month in self.project(inputs, high_assumptions))
                low_impact = low_ebit - base_ebit
                high_impact = high_ebit - base_ebit
                sensitivities.append(
                    SensitivityItem(
                        driver=field_name,
                        label=label,
                        shock=f"{shock:+g}",
                        ebit_impact_usd_low=round(low_impact, 2),
                        ebit_impact_usd_high=round(high_impact, 2),
                        ebit_swing_usd=round(abs(high_impact - low_impact), 2),
                    )
                )
            sensitivities.sort(key=lambda item: item.ebit_swing_usd, reverse=True)

        return ScenarioResult(
            as_of=self.engine.as_of,
            base_period=f"{inputs.base_months[0]}..{inputs.base_months[-1]}",
            horizon_months=horizon,
            currency=self.engine.currency,
            synthetic=self.engine.synthetic,
            baseline=baseline_summary,
            scenarios=summaries,
            monthly=monthly,
            sensitivities=sensitivities,
            assumptions=definitions,
            model_note=MODEL_NOTE,
            lineage=[f"actual:monthly_financials@{m}" for m in inputs.base_months] + ["model:driver-based-forecast@v1"],
        )

    # ------------------------------------------------------------------
    def to_csv(self, result: ScenarioResult) -> str:
        """Flatten every scenario month to CSV (used by the export endpoint)."""
        rows: list[dict] = []
        for scenario_id, months in result.monthly.items():
            for month in months:
                row = month.model_dump()
                row["scenario_id"] = scenario_id
                rows.append(row)
        if not rows:
            return "scenario_id,month\n"
        frame = pd.DataFrame(rows)
        ordered = ["scenario_id"] + [column for column in frame.columns if column != "scenario_id"]
        return frame[ordered].to_csv(index=False)
