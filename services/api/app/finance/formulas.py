"""Small numeric helpers with explicit undefined-value semantics.

Rule of the codebase: **never** turn a zero denominator or a missing input into
a number. Return ``None`` and let the caller record why.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd


@dataclass(frozen=True)
class SafeValue:
    """A value that may legitimately be undefined."""

    value: float | None
    status: str  # "ok" | "undefined" | "missing"
    note: str | None = None


def safe_div(numerator: float | None, denominator: float | None, *, label: str = "denominator") -> SafeValue:
    """Divide, refusing to invent a value when an input is missing or the denominator is 0."""
    if numerator is None or pd.isna(numerator):
        return SafeValue(None, "missing", "the numerator of this ratio is not available")
    if denominator is None or pd.isna(denominator):
        return SafeValue(None, "missing", f"{label} is not available")
    if denominator == 0:
        return SafeValue(None, "undefined", f"{label} is zero, ratio is undefined")
    return SafeValue(float(numerator) / float(denominator), "ok")


def pct_change(current: float | None, previous: float | None, *, label: str = "base period") -> SafeValue:
    """Relative change; undefined when the base is zero or missing."""
    if current is None or previous is None or pd.isna(current) or pd.isna(previous):
        return SafeValue(None, "missing", f"{label} is not available")
    if previous == 0:
        return SafeValue(None, "undefined", f"{label} value is zero, percentage change is undefined")
    return SafeValue((float(current) - float(previous)) / abs(float(previous)), "ok")


def sum_available(values: Iterable[float | None]) -> tuple[float, int]:
    """Sum ignoring missing cells; also return how many cells were missing.

    The caller must surface the missing count (partial coverage) instead of
    silently reporting a smaller total as if it were complete.
    """
    total = 0.0
    missing = 0
    for value in values:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            missing += 1
            continue
        total += float(value)
    return total, missing


def days_in_month(month: str) -> int:
    """Calendar days for a ``YYYY-MM`` label."""
    year, mon = (int(part) for part in month.split("-"))
    return calendar.monthrange(year, mon)[1]


def days_in_months(months: Sequence[str]) -> int:
    return sum(days_in_month(month) for month in months)


def annualise(value: float | None, months: int) -> float | None:
    """Scale a flow to 12 months. ``months`` must be >= 1."""
    if value is None or months <= 0:
        return None
    return float(value) * 12.0 / float(months)


def previous_month(month: str) -> str:
    year, mon = (int(part) for part in month.split("-"))
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def same_month_previous_year(month: str) -> str:
    year, mon = (int(part) for part in month.split("-"))
    return f"{year - 1}-{mon:02d}"


def month_span(start: str, end: str, all_months: Sequence[str]) -> list[str]:
    """Inclusive slice of ``all_months`` between ``start`` and ``end``."""
    months = [m for m in all_months if start <= m <= end]
    return months
