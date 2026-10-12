"""Shared test fixtures: tiny hand-built datasets with known-good numbers.

The tiny dataset is deliberately small so that every expected value can be
derived by hand and written into the test as a literal. Tests that assert on the
generated demo data are separate and never rely on literals.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.data import SyntheticDataset

TINY_MONTHS = ("2024-01", "2024-02", "2024-03")

#: One month of a one-region company. Chosen so that every derived metric is a
#: clean number:
#:   revenue 500, cogs 300, gross profit 200, gross margin 0.40
#:   opex 100, EBITDA 100, D&A 25, EBIT 75, operating margin 0.15
#:   interest 15, taxes 13.2, net income 46.8
#:   coverage 5.00x, AR 250, inventory 150, AP 100, cash 1000, debt 500
DEFAULT_ROW: dict[str, float | str] = {
    "region": "SG",
    "region_name": "Singapore (test)",
    "currency": "SGD",
    "quantity": 100.0,
    "unit_price_local": 10.0,
    "fx_rate_to_usd": 0.5,
    "revenue_usd": 500.0,
    "cogs_material_usd": 200.0,
    "cogs_labor_usd": 50.0,
    "cogs_overhead_usd": 50.0,
    "opex_sales_usd": 50.0,
    "opex_admin_usd": 30.0,
    "opex_rd_usd": 20.0,
    "depreciation_amortization_usd": 25.0,
    "interest_expense_usd": 15.0,
    "cash_taxes_paid_usd": 13.2,
    "annual_interest_rate_pct": 6.0,
    "debt_balance_usd": 500.0,
    "short_term_debt_usd": 100.0,
    "cash_usd": 1000.0,
    "accounts_receivable_usd": 250.0,
    "inventory_usd": 150.0,
    "accounts_payable_usd": 100.0,
    "operating_cash_flow_usd": 60.0,
    "capex_usd": 40.0,
}


def build_tiny_dataset(
    months: tuple[str, ...] = TINY_MONTHS,
    overrides: dict[str, dict[str, float | None]] | None = None,
) -> SyntheticDataset:
    """Build a dataset where ``overrides[month][column]`` replaces a value."""
    overrides = overrides or {}
    rows: list[dict] = []
    for month in months:
        row = {**DEFAULT_ROW, "month": month}
        row.update(overrides.get(month, {}))
        rows.append(row)
    financials = pd.DataFrame(rows)

    budget_rows = []
    for month in months:
        budget_rows.append(
            {
                "month": month,
                "budget_revenue_usd": 600.0,
                "budget_cogs_usd": 360.0,
                "budget_opex_usd": 120.0,
                "budget_depreciation_amortization_usd": 25.0,
                "budget_interest_expense_usd": 15.0,
                "budget_capex_usd": 40.0,
                "budget_note": "test plan",
            }
        )
    budget = pd.DataFrame(budget_rows)

    macro_rows = []
    for index, month in enumerate(months):
        macro_rows.append(
            {
                "series_id": "DFF",
                "title": "Federal Funds Effective Rate",
                "units": "Percent",
                "frequency": "daily",
                "country": "US",
                "observation_date": f"{month}-01",
                "value": 4.0 + 0.1 * index,
                "source_url": "https://fred.stlouisfed.org/series/DFF",
                "is_fixture": True,
                "fetched_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
                "license_note": "test fixture",
            }
        )
    macro = pd.DataFrame(macro_rows)

    profile = {
        "company_id": "TEST-001",
        "display_name": "Test Company (synthetic)",
        "reporting_currency": "USD",
        "local_currencies": ["SGD"],
        "regions": [{"code": "SG", "name": "Singapore (test)", "currency": "SGD"}],
        "period_range": {"start": months[0], "end": months[-1], "months": len(months)},
        "fiscal_year_end": "12-31",
        "synthetic": True,
        "disclaimer": "Test fixture. Not real data.",
    }
    manifest = {"dataset_id": "tiny-test", "synthetic": True, "row_counts": {"monthly_financials": len(rows)}}
    return SyntheticDataset(
        financials=financials, budget=budget, macro=macro, profile=profile, manifest=manifest
    )


def build_long_macro(months: int = 24, series_id: str = "DFF") -> pd.DataFrame:
    """A macro fixture long enough for the year-on-year rate rule (needs 13+)."""
    periods = pd.period_range(start="2023-01", periods=months, freq="M")
    return pd.DataFrame(
        [
            {
                "series_id": series_id,
                "title": "Federal Funds Effective Rate",
                "units": "Percent",
                "frequency": "daily",
                "country": "US",
                "observation_date": f"{period}-01",
                "value": 5.0 + 0.05 * index,
                "source_url": f"https://fred.stlouisfed.org/series/{series_id}",
                "is_fixture": True,
                "fetched_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
                "license_note": "test fixture",
            }
            for index, period in enumerate(periods)
        ]
    )


def with_macro(dataset: SyntheticDataset, macro: pd.DataFrame) -> SyntheticDataset:
    return SyntheticDataset(
        financials=dataset.financials,
        budget=dataset.budget,
        macro=macro,
        profile=dataset.profile,
        manifest=dataset.manifest,
    )


def deterministic_csv(dataset: SyntheticDataset) -> str:
    return dataset.financials.to_csv(index=False)


__all__ = [
    "DEFAULT_ROW",
    "TINY_MONTHS",
    "build_long_macro",
    "build_tiny_dataset",
    "deterministic_csv",
    "np",
    "with_macro",
]
