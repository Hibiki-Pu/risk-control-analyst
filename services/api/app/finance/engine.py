"""Deterministic financial engine.

Everything the product shows or cites is produced here from the tidy fact table.
No LLM participates. Every number carries its unit, period, formula and source
ids so the report layer can verify it and the agent can only quote it.

Definitions (full detail in ``docs/financial-methodology.md``):

* ``revenue``          sum of ``revenue_usd`` over the period/scope.
* ``cogs``             material + labour + production overhead.
* ``gross_profit``     revenue - cogs.
* ``ebitda``           gross_profit - operating expenses (D&A is NOT deducted).
* ``ebit``             ebitda - depreciation & amortisation. Never equals EBITDA.
* ``net_income``       ebit - interest expense - cash taxes paid.
* ``operating_cash_flow``  EBIT + D&A - cash taxes - change in net working capital
                       (a documented proxy, not a statutory cash-flow statement).
* ``dso_days``         average receivables / (revenue / calendar days in period).
* ``dso_days_ending``  same but using the closing receivable balance.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from app.data import SyntheticDataset
from app.finance.formulas import (
    SafeValue,
    days_in_month,
    days_in_months,
    pct_change,
    safe_div,
    same_month_previous_year,
)
from app.schemas import CitedValue, DataLineage, MetricSet, MonthlyPoint, PeriodSeries

ADDITIVE_COLUMNS: dict[str, str] = {
    "revenue": "revenue_usd",
    "cogs_material": "cogs_material_usd",
    "cogs_labor": "cogs_labor_usd",
    "cogs_overhead": "cogs_overhead_usd",
    "opex_sales": "opex_sales_usd",
    "opex_admin": "opex_admin_usd",
    "opex_rd": "opex_rd_usd",
    "dep_amort": "depreciation_amortization_usd",
    "interest_expense": "interest_expense_usd",
    "cash_taxes": "cash_taxes_paid_usd",
    "accounts_receivable": "accounts_receivable_usd",
    "inventory": "inventory_usd",
    "accounts_payable": "accounts_payable_usd",
    "cash": "cash_usd",
    "debt": "debt_balance_usd",
    "short_term_debt": "short_term_debt_usd",
    "capex": "capex_usd",
    "operating_cash_flow": "operating_cash_flow_usd",
}

SOURCE_LABEL = {
    "actual": "actual:monthly_financials",
    "budget": "budget:monthly_budget",
    "derived": "derived:engine",
}

TAX_RATE_USED = 0.22


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Element-wise ratio that yields NaN (never a fake number) on 0/NaN."""
    out = pd.Series(np.nan, index=numerator.index, dtype="float64")
    mask = numerator.notna() & denominator.notna() & (denominator != 0)
    out[mask] = numerator[mask] / denominator[mask]
    return out


class FinancialEngine:
    """Read-only calculator over one dataset."""

    def __init__(self, dataset: SyntheticDataset, dataset_id: str = "synthetic-aurelia-v1", synthetic: bool = True):
        self.dataset = dataset
        self.actuals = dataset.financials.copy()
        self.budget = dataset.budget.copy()
        self.profile = dataset.profile
        self.dataset_id = dataset_id
        self.synthetic = synthetic
        self.currency = str(dataset.profile.get("reporting_currency", "USD"))
        self.months: list[str] = sorted(self.actuals["month"].unique().tolist())
        self.regions: list[str] = sorted(self.actuals["region"].unique().tolist())
        self._monthly_cache: dict[tuple[str, ...], pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # scoping / aggregation
    # ------------------------------------------------------------------
    @property
    def as_of(self) -> str:
        return self.months[-1]

    @property
    def trailing_twelve(self) -> list[str]:
        return self.months[-12:]

    def scope(self, regions: Sequence[str] | None = None, months: Sequence[str] | None = None) -> pd.DataFrame:
        frame = self.actuals
        if regions:
            frame = frame[frame["region"].isin(list(regions))]
        if months:
            frame = frame[frame["month"].isin(list(months))]
        return frame

    def monthly_frame(self, regions: Sequence[str] | None = None) -> pd.DataFrame:
        """Group-level monthly aggregation of the fact table plus derived lines."""
        key = tuple(sorted(regions)) if regions else ("__all__",)
        if key in self._monthly_cache:
            return self._monthly_cache[key].copy()

        frame = self.scope(regions)
        if frame.empty:
            raise ValueError("no rows match the requested scope")

        grouped = frame.groupby("month", sort=True)
        index = pd.Index(sorted(frame["month"].unique()), name="month")
        agg = pd.DataFrame(index=index)
        for name, column in ADDITIVE_COLUMNS.items():
            agg[name] = grouped[column].sum(min_count=1)

        missing = (
            frame[list(ADDITIVE_COLUMNS.values())]
            .isna()
            .groupby(frame["month"])
            .sum()
            .sum(axis=1)
            .reindex(index)
            .fillna(0)
            .astype(int)
        )
        agg["missing_cells"] = missing

        agg["cogs"] = agg[["cogs_material", "cogs_labor", "cogs_overhead"]].sum(axis=1, min_count=1)
        agg["gross_profit"] = agg["revenue"] - agg["cogs"]
        agg["gross_margin"] = _ratio(agg["gross_profit"], agg["revenue"])
        agg["opex"] = agg[["opex_sales", "opex_admin", "opex_rd"]].sum(axis=1, min_count=1)
        agg["ebitda"] = agg["gross_profit"] - agg["opex"]
        agg["ebit"] = agg["ebitda"] - agg["dep_amort"]
        agg["operating_margin"] = _ratio(agg["ebit"], agg["revenue"])
        agg["ebt"] = agg["ebit"] - agg["interest_expense"]
        agg["net_income"] = agg["ebt"] - agg["cash_taxes"]
        agg["net_margin"] = _ratio(agg["net_income"], agg["revenue"])
        agg["free_cash_flow"] = agg["operating_cash_flow"] - agg["capex"]

        opening_ar = agg["accounts_receivable"].shift(1)
        opening_ar.iloc[0] = agg["accounts_receivable"].iloc[0]
        agg["avg_accounts_receivable"] = (opening_ar + agg["accounts_receivable"]) / 2.0
        opening_inv = agg["inventory"].shift(1)
        opening_inv.iloc[0] = agg["inventory"].iloc[0]
        agg["avg_inventory"] = (opening_inv + agg["inventory"]) / 2.0
        opening_ap = agg["accounts_payable"].shift(1)
        opening_ap.iloc[0] = agg["accounts_payable"].iloc[0]
        agg["avg_accounts_payable"] = (opening_ap + agg["accounts_payable"]) / 2.0

        days = pd.Series({month: days_in_month(month) for month in index}, dtype="float64")
        agg["days"] = days
        agg["dso_days"] = _ratio(agg["avg_accounts_receivable"] * days, agg["revenue"])
        agg["dso_days_ending"] = _ratio(agg["accounts_receivable"] * days, agg["revenue"])
        agg["dio_days"] = _ratio(agg["avg_inventory"] * days, agg["cogs"])
        agg["dpo_days"] = _ratio(agg["avg_accounts_payable"] * days, agg["cogs"])
        agg["cash_conversion_cycle_days"] = agg["dso_days"] + agg["dio_days"] - agg["dpo_days"]
        agg["net_debt"] = agg["debt"] - agg["cash"]

        self._monthly_cache[key] = agg
        return agg.copy()

    def select_months(self, start: str | None = None, end: str | None = None, limit: int | None = None) -> list[str]:
        months = [m for m in self.months if (start is None or m >= start) and (end is None or m <= end)]
        if limit:
            months = months[-limit:]
        if not months:
            raise ValueError(f"no months in range {start}..{end}")
        return months

    # ------------------------------------------------------------------
    # metric helpers
    # ------------------------------------------------------------------
    def _source(self, kind: str, months: Iterable[str]) -> list[str]:
        return [f"{SOURCE_LABEL[kind]}@{month}" for month in months]

    def _cited(
        self,
        metric_id: str,
        label: str,
        value: float | None,
        *,
        unit: str,
        period: str,
        formula: str,
        source_ids: list[str],
        basis: str = "actual",
        status: str = "ok",
        note: str | None = None,
    ) -> CitedValue:
        return CitedValue(
            metric_id=metric_id,
            label=label,
            value=None if value is None else round(float(value), 6),
            unit=unit,
            period=period,
            basis=basis,  # type: ignore[arg-type]
            formula=formula,
            source_ids=source_ids,
            status=status,  # type: ignore[arg-type]
            note=note,
            synthetic=self.synthetic,
        )

    @staticmethod
    def _status_of(safe: SafeValue) -> tuple[float | None, str, str | None]:
        return safe.value, safe.status, safe.note

    # ------------------------------------------------------------------
    # period metrics
    # ------------------------------------------------------------------
    def period_span(self, months: Sequence[str]) -> str:
        if len(months) == 1:
            return months[0]
        return f"{months[0]}..{months[-1]}"

    def metrics(
        self,
        start: str | None = None,
        end: str | None = None,
        regions: Sequence[str] | None = None,
        months: Sequence[str] | None = None,
    ) -> MetricSet:
        """Full metric pack for one period (defaults to the latest month)."""
        selected = list(months) if months else self.select_months(start, end)
        frame = self.monthly_frame(regions)
        window = frame.loc[[m for m in selected if m in frame.index]]
        if window.empty:
            raise ValueError("no data in the requested period")

        label = self.period_span(selected)
        sources = self._source("actual", selected)
        total_missing = int(window["missing_cells"].sum())

        def total(column: str) -> float | None:
            """Flow aggregation: sum over the period."""
            value = window[column].sum(min_count=1)
            return None if pd.isna(value) else float(value)

        def closing(column: str) -> float | None:
            """Stock aggregation: a balance-sheet item is a point-in-time value.

            Summing cash or debt across months would produce a meaningless number,
            so the closing balance of the period is used and the formula says so.
            """
            value = frame[column].loc[selected[-1]]
            return None if pd.isna(value) else float(value)

        revenue = total("revenue")
        cogs = total("cogs")
        gross_profit = total("gross_profit")
        opex = total("opex")
        ebitda = total("ebitda")
        ebit = total("ebit")
        interest = total("interest_expense")
        taxes = total("cash_taxes")
        dep_amort = total("dep_amort")
        net_income = total("net_income")
        ocf = total("operating_cash_flow")
        capex = total("capex")
        fcf = None if ocf is None or capex is None else ocf - capex

        days = float(days_in_months(selected))
        first_index = self.months.index(selected[0])
        # Opening balances: for the first period in the dataset there is no
        # comparative, so the closing balance is used and the metric says so.
        if first_index > 0:
            opening_ar: float | None = float(frame["accounts_receivable"].iloc[first_index - 1])
            opening_inv: float | None = float(frame["inventory"].iloc[first_index - 1])
            opening_ap: float | None = float(frame["accounts_payable"].iloc[first_index - 1])
            opening_note: str | None = None
        else:
            opening_ar = opening_inv = opening_ap = None
            opening_note = (
                "no opening balance exists for the first period of the dataset; the closing balance is used"
            )
        closing_ar = float(frame["accounts_receivable"].loc[selected[-1]])
        closing_inv = float(frame["inventory"].loc[selected[-1]])
        closing_ap = float(frame["accounts_payable"].loc[selected[-1]])
        avg_ar = closing_ar if opening_ar is None else (opening_ar + closing_ar) / 2.0
        avg_inv = closing_inv if opening_inv is None else (opening_inv + closing_inv) / 2.0
        avg_ap = closing_ap if opening_ap is None else (opening_ap + closing_ap) / 2.0

        cash = closing("cash")
        debt = closing("debt")
        short_term_debt = closing("short_term_debt")

        values: dict[str, CitedValue] = {}

        partial_note = (
            f"partial coverage: {total_missing} source cell(s) missing in this period; totals exclude the "
            "missing values and are flagged"
            if total_missing
            else None
        )

        def combine(*notes: str | None) -> str | None:
            joined = "; ".join(note for note in notes if note)
            return joined or None

        def add(metric_id: str, lbl: str, value: float | None, unit: str, formula: str, *, status: str = "ok", note: str | None = None, basis: str = "actual") -> None:
            values[metric_id] = self._cited(
                metric_id, lbl, value, unit=unit, period=label, formula=formula,
                source_ids=sources, basis=basis, status=status,
                note=combine(note, partial_note if status == "ok" else None),
            )

        def add_ratio(metric_id: str, lbl: str, num: float | None, den: float | None, denominator_label: str, formula: str) -> None:
            safe = safe_div(num, den, label=denominator_label)
            value, status, note = self._status_of(safe)
            add(metric_id, lbl, value, "pct" if metric_id.endswith("_margin") else "x", formula, status=status, note=note)

        add("revenue", "Revenue", revenue, self.currency, "sum(revenue_usd)")
        add("cogs", "Cost of goods sold", cogs, self.currency, "material + labour + production overhead")
        add("gross_profit", "Gross profit", gross_profit, self.currency, "revenue - cogs")
        add_ratio("gross_margin", "Gross margin", gross_profit, revenue, "revenue", "gross_profit / revenue")
        add("opex", "Operating expenses", opex, self.currency, "sales + admin + R&D")
        add("ebitda", "EBITDA", ebitda, self.currency, "gross_profit - opex (D&A not deducted)")
        add("depreciation_amortization", "Depreciation & amortisation", dep_amort, self.currency, "sum(depreciation_amortization_usd)")
        add("ebit", "EBIT (operating profit)", ebit, self.currency, "ebitda - depreciation & amortisation")
        add_ratio("operating_margin", "Operating margin", ebit, revenue, "revenue", "ebit / revenue")
        add("interest_expense", "Interest expense", interest, self.currency, "sum(interest_expense_usd)")
        add("ebt", "Profit before tax", None if ebit is None or interest is None else ebit - interest, self.currency, "ebit - interest_expense")
        add("cash_taxes", "Cash taxes paid", taxes, self.currency, "sum(cash_taxes_paid_usd)")
        add("net_income", "Net income (proxy)", net_income, self.currency, "ebit - interest - cash taxes paid")
        add_ratio("net_margin", "Net margin", net_income, revenue, "revenue", "net_income / revenue")
        add("operating_cash_flow", "Operating cash flow (proxy)", ocf, self.currency, "ebit + D&A - cash taxes - change in net working capital")
        add("capex", "Capital expenditure", capex, self.currency, "sum(capex_usd)")
        add("free_cash_flow", "Free cash flow (proxy)", fcf, self.currency, "operating_cash_flow - capex")
        add("cash", "Cash (closing)", cash, self.currency, "closing balance of cash_usd at period end (point-in-time, not summed)")
        add("debt", "Total debt (closing)", debt, self.currency, "closing balance of debt_balance_usd at period end (point-in-time, not summed)")
        add(
            "net_debt",
            "Net debt (closing)",
            None if debt is None or cash is None else debt - cash,
            self.currency,
            "total debt - cash",
        )

        add_ratio("interest_coverage", "Interest coverage", ebit, interest, "interest expense", "ebit / interest_expense")
        ebitda_annualised = None if ebitda is None else ebitda * 12.0 / max(len(selected), 1)
        add_ratio("net_leverage", "Net debt / EBITDA (annualised)", None if debt is None or cash is None else debt - cash, ebitda_annualised, "annualised EBITDA", "net_debt / (ebitda x 12 / months)")

        def combine(*notes: str | None) -> str | None:
            joined = "; ".join(note for note in notes if note)
            return joined or None

        dso_safe = safe_div(avg_ar * days, revenue, label="revenue")
        dso_value, dso_status, dso_note = self._status_of(dso_safe)
        add("dso_days", "Days sales outstanding (average receivables)", dso_value, "days", "average receivables / (revenue / days in period)", status=dso_status, note=combine(dso_note, opening_note))

        dso_end_safe = safe_div(closing_ar * days, revenue, label="revenue")
        dso_end_value, dso_end_status, dso_end_note = self._status_of(dso_end_safe)
        add("dso_days_ending", "Days sales outstanding (closing receivables)", dso_end_value, "days", "closing receivables / (revenue / days in period)", status=dso_end_status, note=combine(dso_end_note, opening_note))

        dio_safe = safe_div(avg_inv * days, cogs, label="cost of goods sold")
        dio_value, dio_status, dio_note = self._status_of(dio_safe)
        add("dio_days", "Days inventory outstanding", dio_value, "days", "average inventory / (cogs / days in period)", status=dio_status, note=combine(dio_note, opening_note))

        dpo_safe = safe_div(avg_ap * days, cogs, label="cost of goods sold")
        dpo_value, dpo_status, dpo_note = self._status_of(dpo_safe)
        add("dpo_days", "Days payable outstanding", dpo_value, "days", "average payables / (cogs / days in period)", status=dpo_status, note=combine(dpo_note, opening_note))

        if None in (dso_value, dio_value, dpo_value):
            add("cash_conversion_cycle_days", "Cash conversion cycle", None, "days", "dso + dio - dpo", status="missing", note="one or more working-capital ratios are unavailable")
        else:
            add("cash_conversion_cycle_days", "Cash conversion cycle", dso_value + dio_value - dpo_value, "days", "dso + dio - dpo")

        current_assets = None if None in (cash, closing_ar, closing_inv) else cash + closing_ar + closing_inv
        current_liabilities = None if None in (closing_ap, short_term_debt) else closing_ap + short_term_debt
        current_ratio = safe_div(current_assets, current_liabilities, label="current liabilities")
        value, status, note = self._status_of(current_ratio)
        add("current_ratio", "Current ratio", value, "x", "(cash + receivables + inventory) / (payables + short-term debt)", status=status, note=note)

        # Growth: month-on-month and year-on-year against the previous periods.
        if len(selected) == 1:
            month = selected[0]
            index = self.months.index(month)
            previous = self.months[index - 1] if index > 0 else None
            prior_year = same_month_previous_year(month)
            current_revenue = revenue
            if previous:
                safe = pct_change(current_revenue, float(frame["revenue"].loc[previous]), label="prior month revenue")
                value, status, note = self._status_of(safe)
                add("revenue_mom", "Revenue month-on-month", value, "pct", "revenue_m / revenue_m-1 - 1", status=status, note=note)
            if prior_year in frame.index:
                safe = pct_change(current_revenue, float(frame["revenue"].loc[prior_year]), label="prior-year revenue")
                value, status, note = self._status_of(safe)
                add("revenue_yoy", "Revenue year-on-year", value, "pct", "revenue_m / revenue_m-12 - 1", status=status, note=note)

        # Currency mix (FX exposure visibility).
        mix = self.revenue_by_currency(selected, regions)
        for currency, share in mix.items():
            add(
                f"revenue_share_{currency.lower()}",
                f"Revenue share in {currency}",
                share,
                "pct",
                "revenue in currency / total revenue",
            )

        return MetricSet(
            as_of=self.as_of,
            period=label,
            scope={"regions": list(regions) if regions else "ALL", "months": selected},
            currency=self.currency,
            synthetic=self.synthetic,
            values=values,
            lineage=self._source("actual", selected),
        )

    def revenue_by_currency(self, months: Sequence[str], regions: Sequence[str] | None = None) -> dict[str, float]:
        frame = self.scope(regions, months)
        totals = frame.groupby("currency")["revenue_usd"].sum(min_count=1)
        total = float(totals.sum())
        if total == 0:
            return {}
        return {str(currency): float(value) / total for currency, value in totals.items()}

    def revenue_by_region(self, months: Sequence[str]) -> dict[str, float]:
        frame = self.scope(None, months)
        return {
            str(region): float(value)
            for region, value in frame.groupby("region")["revenue_usd"].sum(min_count=1).items()
        }

    # ------------------------------------------------------------------
    # series
    # ------------------------------------------------------------------
    def series(
        self,
        start: str | None = None,
        end: str | None = None,
        regions: Sequence[str] | None = None,
        months: Sequence[str] | None = None,
        include_budget: bool = True,
    ) -> PeriodSeries:
        selected = list(months) if months else self.select_months(start, end)
        frame = self.monthly_frame(regions)
        budget_indexed = self.budget_series_index() if include_budget else None

        points: list[MonthlyPoint] = []

        def clean(value: float | None) -> float | None:
            return None if value is None or pd.isna(value) else round(float(value), 2)

        def pct_or_none(current: float | None, base: float | None) -> float | None:
            """Relative change; undefined for a zero base (never a fake number)."""
            if current is None or base is None or base == 0:
                return None
            return round((current - base) / abs(base), 6)

        for month in selected:
            if month not in frame.index:
                continue
            row = frame.loc[month]
            index = self.months.index(month)
            previous = self.months[index - 1] if index > 0 else None
            prior_year = same_month_previous_year(month)
            budget_row = budget_indexed.loc[month] if budget_indexed is not None and month in budget_indexed.index else None

            revenue = clean(row["revenue"])
            budget_revenue = clean(budget_row["budget_revenue"]) if budget_row is not None else None
            ebit = clean(row["ebit"])
            budget_ebit = clean(budget_row["budget_ebit"]) if budget_row is not None else None
            previous_revenue = clean(frame["revenue"].loc[previous]) if previous else None
            prior_year_revenue = clean(frame["revenue"].loc[prior_year]) if prior_year in frame.index else None
            points.append(
                MonthlyPoint(
                    month=month,
                    revenue_usd=revenue,
                    cogs_usd=clean(row["cogs"]),
                    gross_profit_usd=clean(row["gross_profit"]),
                    gross_margin_pct=clean(row["gross_margin"]),
                    ebit_usd=ebit,
                    operating_margin_pct=clean(row["operating_margin"]),
                    interest_expense_usd=clean(row["interest_expense"]),
                    net_income_usd=clean(row["net_income"]),
                    operating_cash_flow_usd=clean(row["operating_cash_flow"]),
                    free_cash_flow_usd=clean(row["free_cash_flow"]),
                    dso_days=clean(row["dso_days"]),
                    cash_usd=clean(row["cash"]),
                    budget_revenue_usd=budget_revenue,
                    revenue_variance_usd=None if revenue is None or budget_revenue is None else round(revenue - budget_revenue, 2),
                    revenue_variance_pct=pct_or_none(revenue, budget_revenue),
                    ebit_variance_usd=None if ebit is None or budget_ebit is None else round(ebit - budget_ebit, 2),
                    mom_revenue_pct=pct_or_none(revenue, previous_revenue),
                    yoy_revenue_pct=pct_or_none(revenue, prior_year_revenue),
                )
            )

        return PeriodSeries(
            as_of=self.as_of,
            currency=self.currency,
            synthetic=self.synthetic,
            scope={"regions": list(regions) if regions else "ALL"},
            points=points,
            lineage=self._source("actual", selected) + self._source("budget", selected),
        )

    # ------------------------------------------------------------------
    # budget
    # ------------------------------------------------------------------
    def budget_series_index(self) -> pd.DataFrame:
        if self.budget.empty:
            return pd.DataFrame(index=pd.Index([], name="month"))
        frame = self.budget.set_index("month").copy()
        frame["budget_gross_profit"] = frame["budget_revenue_usd"] - frame["budget_cogs_usd"]
        frame["budget_ebit"] = (
            frame["budget_gross_profit"]
            - frame["budget_opex_usd"]
            - frame["budget_depreciation_amortization_usd"]
        )
        return frame.rename(
            columns={
                "budget_revenue_usd": "budget_revenue",
                "budget_cogs_usd": "budget_cogs",
                "budget_opex_usd": "budget_opex",
                "budget_depreciation_amortization_usd": "budget_dep_amort",
                "budget_interest_expense_usd": "budget_interest",
                "budget_capex_usd": "budget_capex",
            }
        )

    def budget_variance(
        self,
        start: str | None = None,
        end: str | None = None,
        months: Sequence[str] | None = None,
    ) -> MetricSet:
        selected = list(months) if months else self.select_months(start, end)
        label = self.period_span(selected)
        if self.budget.empty:
            # Uploaded datasets carry no plan. Report "not available" instead of
            # comparing actuals against an invented plan.
            values: dict[str, CitedValue] = {}
            for metric_id in ("revenue", "cogs", "opex", "ebit", "capex", "interest_expense"):
                for suffix, unit in (("_variance", self.currency), ("_variance_pct", "pct")):
                    values[f"{metric_id}{suffix}"] = self._cited(
                        f"{metric_id}{suffix}",
                        f"{metric_id.replace('_', ' ').title()} variance vs budget",
                        None,
                        unit=unit,
                        period=label,
                        formula=f"actual({metric_id}) - budget({metric_id})",
                        source_ids=self._source("actual", selected),
                        basis="variance",
                        status="missing",
                        note="No budget layer is available for this dataset, so no variance can be computed.",
                    )
            return MetricSet(
                as_of=self.as_of,
                period=label,
                scope={"regions": "ALL"},
                currency=self.currency,
                synthetic=self.synthetic,
                values=values,
                lineage=self._source("actual", selected),
            )

        actual_frame = self.monthly_frame()
        window = actual_frame.loc[[m for m in selected if m in actual_frame.index]]
        budget_window = self.budget_series_index().loc[[m for m in selected if m in self.budget_series_index().index]]
        label = self.period_span(selected)
        sources = self._source("actual", selected) + self._source("budget", selected)

        def actual(column: str) -> float | None:
            value = window[column].sum(min_count=1)
            return None if pd.isna(value) else float(value)

        def planned(column: str) -> float | None:
            value = budget_window[column].sum(min_count=1)
            return None if pd.isna(value) else float(value)

        def add(metric_id: str, lbl: str, value: float | None, unit: str, formula: str, note: str | None = None) -> None:
            self_add = self._cited(
                metric_id,
                lbl,
                value,
                unit=unit,
                period=label,
                formula=formula,
                source_ids=sources,
                basis="variance",
                note=note,
            )
            values[metric_id] = self_add

        values: dict[str, CitedValue] = {}
        pairs = [
            ("revenue", "Revenue", "revenue", "budget_revenue", "favorable when actual > plan"),
            ("cogs", "Cost of goods sold", "cogs", "budget_cogs", "favorable when actual < plan"),
            ("opex", "Operating expenses", "opex", "budget_opex", "favorable when actual < plan"),
            ("ebit", "EBIT", "ebit", "budget_ebit", "favorable when actual > plan"),
            ("capex", "Capital expenditure", "capex", "budget_capex", "favorable when actual < plan"),
            ("interest_expense", "Interest expense", "interest_expense", "budget_interest", "favorable when actual < plan"),
        ]
        for metric_id, lbl, actual_col, budget_col, sign_note in pairs:
            actual_value = actual(actual_col)
            budget_value = planned(budget_col)
            variance = None if actual_value is None or budget_value is None else actual_value - budget_value
            add(
                f"{metric_id}_variance",
                f"{lbl} variance vs budget",
                variance,
                self.currency,
                f"actual({metric_id}) - budget({metric_id})",
                note=sign_note,
            )
            safe = safe_div(variance, abs(budget_value) if budget_value is not None else None, label="budget value")
            value, status, ratio_note = self._status_of(safe)
            add(
                f"{metric_id}_variance_pct",
                f"{lbl} variance vs budget (%)",
                value,
                "pct",
                "(actual - budget) / |budget|",
                note=ratio_note or sign_note,
            )
            values[f"{metric_id}_variance_pct"].status = status  # type: ignore[assignment]

        return MetricSet(
            as_of=self.as_of,
            period=label,
            scope={"regions": "ALL"},
            currency=self.currency,
            synthetic=self.synthetic,
            values=values,
            lineage=sources,
        )

    # ------------------------------------------------------------------
    # lineage
    # ------------------------------------------------------------------
    def lineage(self) -> list[DataLineage]:
        profile = self.profile
        return [
            DataLineage(
                dataset_id=self.dataset_id,
                name="Monthly financial actuals",
                kind="synthetic_seed",
                origin="app/data/synthetic.py (seed 20260101)",
                as_of=self.as_of,
                rows=int(len(self.actuals)),
                synthetic=True,
                columns=sorted(self.actuals.columns.tolist()),
                notes=[
                    "Fictional South-East Asian consumer-goods group; regions SG / TH / VN.",
                    "One declared gap: TH 2024-07 inventory is intentionally missing.",
                    f"Reporting currency {self.currency}; local currencies {profile.get('local_currencies')}.",
                ],
            ),
            DataLineage(
                dataset_id=self.dataset_id,
                name="Monthly budget layer",
                kind="synthetic_seed",
                origin="app/data/synthetic.py (seed 20260101)",
                as_of=self.as_of,
                rows=int(len(self.budget)),
                synthetic=True,
                columns=sorted(self.budget.columns.tolist()),
                notes=["Group-level plan only; no regional budget split is shipped."],
            ),
            DataLineage(
                dataset_id="macro-fixtures-v1",
                name="Macro market fixtures",
                kind="market_fixture",
                origin="app/data/synthetic.py + services/api/app/market/fixtures.py",
                as_of=self.as_of,
                rows=int(len(self.dataset.macro)),
                synthetic=True,
                columns=sorted(self.dataset.macro.columns.tolist()),
                notes=[
                    "Series metadata matches the public FRED series ids, but the shipped values are DEMO fixtures.",
                    "Live values are only served when FRED_API_KEY is configured; provenance then reports is_fixture=false.",
                ],
            ),
        ]
