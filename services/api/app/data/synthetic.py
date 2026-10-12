"""Synthetic Company generator.

A fictional South-East Asian consumer-goods group ("Aurelia Consumer Goods
Pte. Ltd. — SYNTHETIC DEMO") with 24 months of monthly actuals, a budget layer
and a macro fixture set.

Design goals
------------
1. **Deterministic** — one fixed seed reproduces byte-identical CSVs.
2. **Financially coherent** — revenue always equals quantity x price x fx; the
   cash walk ties to EBIT, working capital, capex and debt movements.
3. **Interesting for risk control** — the series deliberately contains margin
   compression, DSO creep, a rate-hike cycle, an FX headwind, a capex spike and
   a budget miss, so the risk register has something real to flag.
4. **Honest** — one working-capital cell is intentionally missing and declared
   in ``DECLARED_GAPS``; everything is flagged synthetic.

Nothing in this file represents a real company.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.data import SyntheticDataset

SEED = 20260101
START_PERIOD = "2023-01"
N_MONTHS = 24
REPORTING_CURRENCY = "USD"
OPENING_CASH_USD = 950_000.0
OPENING_DEBT_USD = 950_000.0
TAX_RATE = 0.22
GENERATOR_VERSION = "1.0.0"

MONEY_COLUMNS = (
    "revenue_usd",
    "cogs_material_usd",
    "cogs_labor_usd",
    "cogs_overhead_usd",
    "opex_sales_usd",
    "opex_admin_usd",
    "opex_rd_usd",
    "depreciation_amortization_usd",
    "interest_expense_usd",
    "cash_taxes_paid_usd",
    "cash_usd",
    "accounts_receivable_usd",
    "inventory_usd",
    "accounts_payable_usd",
    "short_term_debt_usd",
    "debt_balance_usd",
    "capex_usd",
)

#: Cells intentionally left empty so the missing-data policy is exercised.
DECLARED_GAPS: list[dict[str, str]] = [
    {
        "region": "TH",
        "month": "2024-07",
        "column": "inventory_usd",
        "reason": "Declared demo gap: the Thailand stock count was not closed before the cut-off. "
        "Working-capital metrics for this region-month must report 'partial coverage'.",
    }
]

SEASONALITY = {
    1: 0.94,
    2: 0.88,
    3: 1.00,
    4: 1.00,
    5: 1.02,
    6: 1.00,
    7: 0.99,
    8: 1.02,
    9: 1.03,
    10: 1.05,
    11: 1.10,
    12: 1.12,
}


@dataclass(frozen=True)
class Region:
    code: str
    name: str
    currency: str
    base_quantity: float
    base_unit_price_local: float
    base_fx_to_usd: float
    annual_volume_growth: float
    seasonality_amplitude: float
    price_drift_per_year: float


REGIONS: tuple[Region, ...] = (
    Region("SG", "Singapore (regional HQ)", "SGD", 12_500, 8.60, 0.7500, 0.030, 0.35, 0.020),
    Region("TH", "Thailand", "THB", 31_000, 95.00, 0.02850, 0.070, 0.45, 0.025),
    Region("VN", "Vietnam", "VND", 12_000, 210_000.00, 0.0000410, 0.140, 0.30, 0.045),
)


def _ramp(t: int, start: int, end: int) -> float:
    """Linear ramp from 0 at ``start`` to 1 at ``end`` (clipped)."""
    if end <= start:
        return 1.0 if t >= end else 0.0
    return float(np.clip((t - start) / (end - start), 0.0, 1.0))


#: Funding-centre weights. Balance-sheet items (cash, debt, capex) are allocated
#: with these weights so that group totals are exact sums of the regional rows.
REGION_WEIGHTS: dict[str, float] = {"SG": 0.50, "TH": 0.30, "VN": 0.20}


def _month_labels(n_months: int | None = None, start: str = START_PERIOD) -> list[str]:
    count = N_MONTHS if n_months is None else n_months
    periods = pd.period_range(start=start, periods=count, freq="M")
    return [str(p) for p in periods]


# --------------------------------------------------------------------------
# Driver curves (all deterministic, documented in docs/data-dictionary.md)
# --------------------------------------------------------------------------
def _volume_index(region: Region, t: int, rng: np.random.Generator, month: int) -> float:
    growth = (1.0 + region.annual_volume_growth) ** (t / 12.0)
    if region.code == "SG":  # soft demand in the second year
        growth *= 1.0 - 0.014 * max(0, t - 11)
    if region.code == "VN":  # fast ramp, then plateau
        growth *= 1.0 + 0.004 * min(t, 14)
    seasonal = 1.0 + region.seasonality_amplitude * (SEASONALITY[month] - 1.0)
    noise = 1.0 + rng.normal(0.0, 0.018)
    return growth * seasonal * noise


def _unit_price_index(region: Region, t: int) -> float:
    index = (1.0 + region.price_drift_per_year) ** (t / 12.0)
    if region.code == "SG" and 13 <= t <= 17:  # promotional price reset in 2024 H1
        index *= 0.975
    if region.code == "TH" and t >= 18:  # price increase partly absorbed by the market
        index *= 0.99
    return index


def _material_index(t: int) -> float:
    """Input-cost inflation: ~9% over 24 months, front-loaded into 2023 H2."""
    return 1.0 + 0.0028 * t + 0.025 * _ramp(t, 5, 18)


def _labor_index(t: int) -> float:
    """Wage inflation with a statutory minimum-wage step in 2024-03 (t=14)."""
    step = 0.022 if t >= 14 else 0.0
    return 1.0 + 0.0026 * t + step


def _fx_index(region: Region, t: int) -> float:
    """USD per 1 unit of local currency (a fall = local currency depreciation)."""
    if region.code == "SG":
        return 1.0 - 0.010 * _ramp(t, 8, 20)
    if region.code == "TH":
        return 1.0 - 0.062 * _ramp(t, 12, 19)
    return 1.0 - 0.048 * _ramp(t, 15, 23)


def _dso_days(t: int) -> float:
    """Collection performance deteriorates through 2024."""
    return 45.0 + 23.0 * _ramp(t, 8, 23)


def _dio_days(t: int) -> float:
    return 62.0 + 16.0 * _ramp(t, 10, 23)


def _dpo_days(t: int) -> float:
    """Suppliers are paid faster than before: a quiet cash-flow squeeze."""
    return 52.0 - 9.0 * _ramp(t, 12, 23)


def _policy_rate_pct(t: int) -> float:
    """Group weighted cost of debt: hiked from 6.5% to 9.0% during 2024."""
    if t < 5:
        return 6.50
    if t < 8:
        return 7.00
    if t < 11:
        return 7.75
    if t < 14:
        return 8.50
    return 9.00


def _debt_path_usd(t: int) -> float:
    debt = OPENING_DEBT_USD
    debt += 180_000.0 if t >= 2 else 0.0    # 2024-03: capacity expansion tranche
    debt += 150_000.0 if t >= 8 else 0.0    # 2024-09: additional working-capital line
    debt -= 60_000.0 if t >= 20 else 0.0    # 2024-09..: scheduled repayment
    return debt


def _capex_usd(t: int) -> float:
    base = 26_000.0
    if t == 8:
        return base + 185_000.0
    if t == 9:
        return base + 95_000.0
    if t >= 10:
        return base * 1.15
    return base


def _opex_ratios(t: int) -> tuple[float, float, float]:
    """(sales, admin, R&D) as a share of revenue."""
    admin = 0.055
    if t >= 15:  # shared-service build-out in 2024-04
        admin = 0.060
    return 0.080, admin, 0.020


# --------------------------------------------------------------------------
# Actuals
# --------------------------------------------------------------------------
def build_financials(seed: int = SEED, n_months: int = N_MONTHS) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = _month_labels(n_months)
    rows: list[dict] = []

    for region in REGIONS:
        weight = REGION_WEIGHTS[region.code]
        cash = OPENING_CASH_USD * weight
        for t, month_label in enumerate(months):
            month_num = int(month_label.split("-")[1])
            quantity = region.base_quantity * _volume_index(region, t, rng, month_num)
            unit_price_local = region.base_unit_price_local * _unit_price_index(region, t)
            fx = region.base_fx_to_usd * _fx_index(region, t)

            revenue = quantity * unit_price_local * fx
            material = revenue * 0.520 * _material_index(t)
            labor = revenue * 0.110 * _labor_index(t)
            overhead = revenue * 0.090 * (1.0 + 0.0025 * t)
            cogs = material + labor + overhead

            opex_sales_r, opex_admin_r, opex_rd_r = _opex_ratios(t)
            opex_sales = revenue * opex_sales_r
            opex_admin = revenue * opex_admin_r
            opex_rd = revenue * opex_rd_r
            dep_amort = revenue * 0.015

            ebit = revenue - cogs - opex_sales - opex_admin - opex_rd - dep_amort
            debt = _debt_path_usd(t) * weight
            rate = _policy_rate_pct(t)
            interest = debt * rate / 100.0 / 12.0
            pretax = ebit - interest
            taxes = max(pretax, 0.0) * TAX_RATE

            ar = revenue * _dso_days(t) / 30.0
            inventory = cogs * _dio_days(t) / 30.0
            ap = cogs * _dpo_days(t) / 30.0
            capex = _capex_usd(t) * weight

            prev = rows[-1] if rows and rows[-1]["region"] == region.code else None
            previous_debt = prev["debt_balance_usd"] if prev else OPENING_DEBT_USD * weight
            if prev is not None:
                delta_nwc = (
                    (ar + inventory - ap)
                    - (prev["accounts_receivable_usd"] + prev["inventory_usd"] - prev["accounts_payable_usd"])
                )
            else:
                # Opening balance sheet: the first month has no comparative, so
                # the working-capital build of month 1 is not a cash movement.
                delta_nwc = 0.0
            ocf = ebit + dep_amort - taxes - delta_nwc
            cash = cash + ocf - capex + (debt - previous_debt)

            rows.append(
                {
                    "month": month_label,
                    "region": region.code,
                    "region_name": region.name,
                    "currency": region.currency,
                    "quantity": round(quantity, 2),
                    "unit_price_local": round(unit_price_local, 4),
                    "fx_rate_to_usd": round(fx, 10),
                    "revenue_usd": round(revenue, 2),
                    "cogs_material_usd": round(material, 2),
                    "cogs_labor_usd": round(labor, 2),
                    "cogs_overhead_usd": round(overhead, 2),
                    "opex_sales_usd": round(opex_sales, 2),
                    "opex_admin_usd": round(opex_admin, 2),
                    "opex_rd_usd": round(opex_rd, 2),
                    "depreciation_amortization_usd": round(dep_amort, 2),
                    "interest_expense_usd": round(interest, 2),
                    "cash_taxes_paid_usd": round(taxes, 2),
                    "annual_interest_rate_pct": rate,
                    "debt_balance_usd": round(debt, 2),
                    "short_term_debt_usd": round(debt * 0.35, 2),
                    "cash_usd": round(cash, 2),
                    "accounts_receivable_usd": round(ar, 2),
                    "inventory_usd": round(inventory, 2),
                    "accounts_payable_usd": round(ap, 2),
                    "operating_cash_flow_usd": round(ocf, 2),
                    "capex_usd": round(capex, 2),
                }
            )

    frame = pd.DataFrame(rows)
    for gap in DECLARED_GAPS:
        mask = (frame["region"] == gap["region"]) & (frame["month"] == gap["month"])
        frame.loc[mask, gap["column"]] = np.nan
    for column in MONEY_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


# --------------------------------------------------------------------------
# Budget layer
# --------------------------------------------------------------------------
def build_budget(financials: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    grouped = {month: grp for month, grp in financials.groupby("month")}
    months = sorted(grouped)
    for index, month in enumerate(months):
        actual = grouped[month]
        prior_year_month = months[index - 12] if index >= 12 else None
        if prior_year_month is not None:
            plan_revenue = float(grouped[prior_year_month]["revenue_usd"].sum()) * 1.12
            plan_gross_margin = 0.285
            plan_opex_ratio = 0.150
        else:
            plan_revenue = float(actual["revenue_usd"].sum()) * 0.985
            plan_gross_margin = 0.275
            plan_opex_ratio = 0.152
        rows.append(
            {
                "month": month,
                "budget_revenue_usd": round(plan_revenue, 2),
                "budget_cogs_usd": round(plan_revenue * (1.0 - plan_gross_margin), 2),
                "budget_opex_usd": round(plan_revenue * plan_opex_ratio, 2),
                "budget_depreciation_amortization_usd": round(plan_revenue * 0.015, 2),
                "budget_interest_expense_usd": round(_debt_path_usd(index) * 0.070 / 12.0, 2),
                "budget_capex_usd": round(30_000.0, 2),
                "budget_note": (
                    "Plan built on prior-year revenue growth with a target gross margin and operating-expense "
                    "ratio set by the budget committee; the parameter values are documented in "
                    "docs/financial-methodology.md."
                ),
            }
        )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Macro fixtures
# --------------------------------------------------------------------------
MACRO_SERIES_META: list[dict[str, str]] = [
    {
        "series_id": "DFF",
        "title": "Federal Funds Effective Rate",
        "units": "Percent",
        "frequency": "daily",
        "country": "US",
        "source_url": "https://fred.stlouisfed.org/series/DFF",
    },
    {
        "series_id": "DGS10",
        "title": "10-Year Treasury Constant Maturity Rate",
        "units": "Percent",
        "frequency": "daily",
        "country": "US",
        "source_url": "https://fred.stlouisfed.org/series/DGS10",
    },
    {
        "series_id": "CPIAUCSL",
        "title": "Consumer Price Index for All Urban Consumers: All Items",
        "units": "Index 1982-1984=100",
        "frequency": "monthly",
        "country": "US",
        "source_url": "https://fred.stlouisfed.org/series/CPIAUCSL",
    },
    {
        "series_id": "PPIACO",
        "title": "Producer Price Index by Commodity: All Commodities",
        "units": "Index 1982=100",
        "frequency": "monthly",
        "country": "US",
        "source_url": "https://fred.stlouisfed.org/series/PPIACO",
    },
    {
        "series_id": "DTWEXBGS",
        "title": "Nominal Broad U.S. Dollar Index",
        "units": "Index Jan 2006=100",
        "frequency": "daily",
        "country": "US",
        "source_url": "https://fred.stlouisfed.org/series/DTWEXBGS",
    },
    {
        "series_id": "DEXTHUS",
        "title": "U.S. Dollars to One Thai Baht (inverted series: THB per USD shown)",
        "units": "Thai Baht to One U.S. Dollar",
        "frequency": "daily",
        "country": "TH",
        "source_url": "https://fred.stlouisfed.org/series/DEXTHUS",
    },
    {
        "series_id": "DEXSIUS",
        "title": "Singapore Dollars to One U.S. Dollar",
        "units": "Singapore Dollars to One U.S. Dollar",
        "frequency": "daily",
        "country": "SG",
        "source_url": "https://fred.stlouisfed.org/series/DEXSIUS",
    },
]

# Hand-built fixture levels. They approximate the shape of the real series but
# are NOT live values and are always served with ``is_fixture=true``.
_MACRO_LEVELS: dict[str, list[float]] = {
    "DFF": [
        4.33, 4.57, 4.65, 5.08, 5.08, 5.08, 5.30, 5.33, 5.33, 5.33, 5.33, 5.33,
        5.33, 5.33, 5.33, 5.33, 5.33, 5.33, 5.33, 5.33, 5.13, 4.83, 4.83, 4.83,
    ],
    "DGS10": [
        3.52, 3.92, 3.55, 3.44, 3.70, 3.84, 3.97, 4.25, 4.57, 4.93, 4.45, 3.88,
        4.05, 4.21, 4.20, 4.68, 4.51, 4.36, 4.20, 3.89, 4.02, 4.28, 4.42, 4.38,
    ],
    "CPIAUCSL": [
        299.17, 300.84, 301.84, 303.36, 304.13, 305.11, 305.69, 307.03, 307.79, 307.67, 307.05, 306.75,
        308.42, 310.33, 312.23, 313.55, 314.07, 314.18, 314.54, 315.30, 315.66, 315.95, 316.44, 317.60,
    ],
    "PPIACO": [
        253.6, 253.1, 251.9, 252.8, 250.6, 250.9, 253.5, 256.4, 258.1, 256.2, 254.1, 252.8,
        253.9, 256.1, 258.9, 261.2, 258.7, 257.9, 259.4, 258.1, 256.6, 257.8, 259.2, 261.0,
    ],
    "DTWEXBGS": [
        120.5, 121.8, 120.9, 120.1, 121.4, 120.7, 118.9, 120.6, 123.1, 124.3, 122.4, 120.2,
        121.6, 122.4, 123.0, 124.8, 125.6, 126.3, 125.1, 123.5, 121.9, 123.6, 126.1, 127.7,
    ],
    "DEXTHUS": [
        33.2, 34.1, 34.3, 34.1, 34.5, 35.1, 34.4, 35.0, 36.4, 36.2, 35.3, 34.6,
        35.0, 35.8, 36.3, 36.9, 36.6, 36.7, 36.2, 34.8, 33.4, 34.2, 34.6, 34.3,
    ],
    "DEXSIUS": [
        1.318, 1.335, 1.330, 1.332, 1.345, 1.351, 1.328, 1.352, 1.364, 1.370, 1.340, 1.328,
        1.333, 1.344, 1.346, 1.358, 1.352, 1.353, 1.345, 1.318, 1.302, 1.312, 1.340, 1.352,
    ],
}


def build_macro(n_months: int = N_MONTHS) -> pd.DataFrame:
    months = _month_labels(n_months)
    fetched_at = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    rows: list[dict] = []
    for meta in MACRO_SERIES_META:
        levels = _MACRO_LEVELS[meta["series_id"]]
        for month, value in zip(months, levels):
            rows.append(
                {
                    "series_id": meta["series_id"],
                    "title": meta["title"],
                    "units": meta["units"],
                    "frequency": meta["frequency"],
                    "country": meta["country"],
                    "observation_date": f"{month}-01",
                    "value": value,
                    "source_url": meta["source_url"],
                    "is_fixture": True,
                    "fetched_at": fetched_at,
                    "license_note": "FRED series metadata is public; the numeric values shipped here are "
                    "hand-built DEMO fixtures, not live observations.",
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Profile / manifest / persistence
# --------------------------------------------------------------------------
def build_profile() -> dict:
    return {
        "company_id": "SYNTH-AURELIA-001",
        "display_name": "Aurelia Consumer Goods Pte. Ltd. (Synthetic Demo)",
        "display_name_zh": "奥瑞利亚消费品集团（合成演示数据）",
        "industry": "Consumer packaged goods (household & personal care)",
        "regions": [{"code": r.code, "name": r.name, "currency": r.currency} for r in REGIONS],
        "reporting_currency": REPORTING_CURRENCY,
        "local_currencies": sorted({r.currency for r in REGIONS}),
        "fiscal_year_end": "12-31",
        "period_range": {"start": _month_labels()[0], "end": _month_labels()[-1], "months": N_MONTHS},
        "consolidation_note": "Regions are funding centres with fixed weights (SG 50%, TH 30%, VN 20%) applied to "
        "cash, debt and capex, so every group total is the exact sum of the regional rows.",
        "synthetic": True,
        "disclaimer": "Every figure in this dataset is computer generated for demonstration. The company is "
        "fictional and the macro values are fixtures, not live market data.",
        "generator": {"module": "app.data.synthetic", "version": GENERATOR_VERSION, "seed": SEED},
    }


def build_manifest(financials: pd.DataFrame, budget: pd.DataFrame, macro: pd.DataFrame) -> dict:
    return {
        "dataset_id": "synthetic-aurelia-v1",
        "generated_by": "app.data.synthetic",
        "generator_version": GENERATOR_VERSION,
        "seed": SEED,
        "period": {"start": _month_labels()[0], "end": _month_labels()[-1], "months": N_MONTHS},
        "reporting_currency": REPORTING_CURRENCY,
        "synthetic": True,
        "row_counts": {
            "monthly_financials": int(len(financials)),
            "monthly_budget": int(len(budget)),
            "macro_series": int(len(macro)),
        },
        "declared_gaps": DECLARED_GAPS,
        "files": [
            {"name": "monthly_financials.csv", "rows": int(len(financials))},
            {"name": "monthly_budget.csv", "rows": int(len(budget))},
            {"name": "macro_series.csv", "rows": int(len(macro))},
        ],
    }


def generate_dataset(seed: int = SEED, n_months: int = N_MONTHS) -> SyntheticDataset:
    global SEED, N_MONTHS  # noqa: PLW0603 - module level contract for regeneration
    SEED, N_MONTHS = seed, n_months
    financials = build_financials(seed=seed, n_months=n_months)
    budget = build_budget(financials)
    macro = build_macro(n_months=n_months)
    return SyntheticDataset(
        financials=financials,
        budget=budget,
        macro=macro,
        profile=build_profile(),
        manifest=build_manifest(financials, budget, macro),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def write_dataset(dataset: SyntheticDataset, target_dir: Path) -> dict:
    target_dir.mkdir(parents=True, exist_ok=True)
    financials_path = target_dir / "monthly_financials.csv"
    budget_path = target_dir / "monthly_budget.csv"
    macro_path = target_dir / "macro_series.csv"
    profile_path = target_dir / "company_profile.json"

    dataset.financials.to_csv(financials_path, index=False, encoding="utf-8")
    dataset.budget.to_csv(budget_path, index=False, encoding="utf-8")
    dataset.macro.to_csv(macro_path, index=False, encoding="utf-8")
    profile_path.write_text(json.dumps(dataset.profile, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = dict(dataset.manifest)
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["sha256"] = {
        path.name: _sha256(path)
        for path in (financials_path, budget_path, macro_path, profile_path)
    }
    (target_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def load_dataset(source_dir: Path) -> SyntheticDataset:
    financials = pd.read_csv(source_dir / "monthly_financials.csv")
    budget = pd.read_csv(source_dir / "monthly_budget.csv")
    macro = pd.read_csv(source_dir / "macro_series.csv")
    profile = json.loads((source_dir / "company_profile.json").read_text(encoding="utf-8"))
    manifest_path = source_dir / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return SyntheticDataset(
        financials=financials, budget=budget, macro=macro, profile=profile, manifest=manifest
    )


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate_dataset(dataset: SyntheticDataset, revenue_tolerance: float = 1.0) -> list[str]:
    """Return a list of human-readable issues (empty means the data is clean)."""
    issues: list[str] = []
    frame = dataset.financials
    required = {"month", "region", "currency", "quantity", "unit_price_local", "fx_rate_to_usd", "revenue_usd"}
    missing_columns = required - set(frame.columns)
    if missing_columns:
        issues.append(f"missing required columns: {sorted(missing_columns)}")
        return issues

    negative_qty = frame[frame["quantity"] <= 0]
    if not negative_qty.empty:
        issues.append(f"{len(negative_qty)} rows have non-positive quantity")

    bad_fx = frame[frame["fx_rate_to_usd"] <= 0]
    if not bad_fx.empty:
        issues.append(f"{len(bad_fx)} rows have non-positive fx_rate_to_usd")

    if frame["revenue_usd"].isna().any():
        issues.append("revenue_usd contains missing values")

    expected = frame["quantity"] * frame["unit_price_local"] * frame["fx_rate_to_usd"]
    deviation = (expected - frame["revenue_usd"]).abs()
    if (deviation > revenue_tolerance).any():
        worst = float(deviation.max())
        issues.append(f"revenue identity (qty x price x fx) violated by up to {worst:.2f} USD")

    declared = {(g["region"], g["month"], g["column"]) for g in DECLARED_GAPS}
    for column in MONEY_COLUMNS:
        if column not in frame.columns:
            continue
        nulls = frame[frame[column].isna()]
        for _, row in nulls.iterrows():
            if (row["region"], row["month"], column) not in declared:
                issues.append(f"undeclared missing value: {column} for {row['region']} {row['month']}")

    for region in REGIONS:
        subset = frame[frame["region"] == region.code]
        if subset.empty:
            issues.append(f"no rows for region {region.code}")
        if set(subset["currency"].unique()) != {region.currency}:
            issues.append(f"currency mismatch for region {region.code}")

    if dataset.budget["month"].nunique() != frame["month"].nunique():
        issues.append("budget and actuals cover a different number of months")

    return issues
