"""Upload validation.

An uploaded file is never trusted: it is parsed, checked against the data
contract, and only then activated. Failures are reported row by row instead of
being silently coerced.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

REQUIRED_COLUMNS: tuple[str, ...] = (
    "month",
    "region",
    "currency",
    "quantity",
    "unit_price_local",
    "fx_rate_to_usd",
    "revenue_usd",
    "cogs_material_usd",
    "cogs_labor_usd",
    "cogs_overhead_usd",
    "opex_sales_usd",
    "opex_admin_usd",
    "opex_rd_usd",
)

OPTIONAL_COLUMNS: tuple[str, ...] = (
    "region_name",
    "depreciation_amortization_usd",
    "interest_expense_usd",
    "cash_taxes_paid_usd",
    "annual_interest_rate_pct",
    "debt_balance_usd",
    "short_term_debt_usd",
    "cash_usd",
    "accounts_receivable_usd",
    "inventory_usd",
    "accounts_payable_usd",
    "operating_cash_flow_usd",
    "capex_usd",
)

ZERO_FILL_COLUMNS: tuple[str, ...] = (
    "depreciation_amortization_usd",
    "interest_expense_usd",
    "cash_taxes_paid_usd",
    "capex_usd",
)


@dataclass
class IngestIssue:
    severity: str  # "error" | "warning"
    message: str
    row: int | None = None


@dataclass
class IngestReport:
    filename: str
    rows: int = 0
    columns: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    issues: list[IngestIssue] = field(default_factory=list)
    preview: list[dict] = field(default_factory=list)
    months: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.missing_required and not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "rows": self.rows,
            "columns": self.columns,
            "missing_required": self.missing_required,
            "months": self.months,
            "regions": self.regions,
            "passed": self.passed,
            "issues": [issue.__dict__ for issue in self.issues],
            "preview": self.preview,
        }


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(content))
    return pd.read_csv(io.BytesIO(content))


def validate_frame(frame: pd.DataFrame, filename: str = "upload.csv") -> tuple[IngestReport, pd.DataFrame]:
    report = IngestReport(filename=filename)
    frame = frame.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    report.columns = list(frame.columns)

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    report.missing_required = missing
    if missing:
        report.issues.append(
            IngestIssue("error", f"Required column(s) missing: {', '.join(missing)}. See docs/data-dictionary.md.")
        )
        return report, frame

    for column in REQUIRED_COLUMNS:
        if frame[column].isna().any():
            report.issues.append(
                IngestIssue("warning", f"{column} has {int(frame[column].isna().sum())} missing value(s).")
            )

    for column in OPTIONAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = 0.0 if column in ZERO_FILL_COLUMNS else pd.NA
    frame["region_name"] = frame.get("region_name", frame["region"])

    month_pattern = frame["month"].astype(str).str.match(r"^\d{4}-(0[1-9]|1[0-2])$")
    if not month_pattern.all():
        bad = frame.loc[~month_pattern, "month"].astype(str).head(3).tolist()
        report.issues.append(IngestIssue("error", f"month must be YYYY-MM; offenders: {bad}"))

    for column in ("quantity", "unit_price_local", "fx_rate_to_usd", "revenue_usd"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    numeric_columns = [
        column
        for column in frame.columns
        if column.endswith("_usd") and column not in {"revenue_usd"}
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if (frame["quantity"] <= 0).any():
        rows = frame.index[frame["quantity"] <= 0].tolist()[:3]
        report.issues.append(IngestIssue("error", "quantity must be positive", row=int(rows[0]) if rows else None))
    if (frame["fx_rate_to_usd"] <= 0).any():
        report.issues.append(IngestIssue("error", "fx_rate_to_usd must be positive"))

    expected = frame["quantity"] * frame["unit_price_local"] * frame["fx_rate_to_usd"]
    deviation = (expected - frame["revenue_usd"]).abs()
    tolerance = 1.0
    if (deviation > tolerance).any():
        offenders = deviation[deviation > tolerance].index.tolist()[:3]
        report.issues.append(
            IngestIssue(
                "warning",
                f"revenue_usd does not equal quantity x unit_price_local x fx_rate_to_usd (tolerance {tolerance}) "
                f"for {len(offenders)} row(s). The engine will recompute revenue from the drivers.",
                row=int(offenders[0]) if offenders else None,
            )
        )
        frame["revenue_usd"] = expected.round(2)

    duplicates = frame.duplicated(subset=["month", "region"]).sum()
    if duplicates:
        report.issues.append(
            IngestIssue("error", f"{int(duplicates)} duplicate (month, region) row(s); the fact table must be unique.")
        )

    currency_per_region = frame.groupby("region")["currency"].nunique()
    mixed = currency_per_region[currency_per_region > 1]
    for region in mixed.index.tolist():
        report.issues.append(
            IngestIssue("warning", f"region {region} reports more than one currency; local-currency FX exposure "
                                   "will be ambiguous.")
        )

    report.rows = int(len(frame))
    report.months = sorted(frame["month"].astype(str).unique().tolist())
    report.regions = sorted(frame["region"].astype(str).unique().tolist())
    report.preview = frame.head(5).astype(object).where(pd.notna(frame.head(5)), None).to_dict(orient="records")
    return report, frame


def ingest(content: bytes, filename: str) -> tuple[IngestReport, pd.DataFrame]:
    frame = read_table(content, filename)
    return validate_frame(frame, filename)
