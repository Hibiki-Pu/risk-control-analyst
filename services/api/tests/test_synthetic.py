"""Tests for the synthetic data generator: determinism, coherence, honesty."""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.synthetic import (
    DECLARED_GAPS,
    REGIONS,
    generate_dataset,
    load_dataset,
    validate_dataset,
    write_dataset,
)


def test_generation_is_deterministic() -> None:
    first = generate_dataset(seed=20260101)
    second = generate_dataset(seed=20260101)
    pd.testing.assert_frame_equal(first.financials, second.financials)
    pd.testing.assert_frame_equal(first.budget, second.budget)
    pd.testing.assert_frame_equal(first.macro, second.macro)


def test_different_seed_changes_the_data() -> None:
    first = generate_dataset(seed=1)
    second = generate_dataset(seed=2)
    assert not first.financials["revenue_usd"].equals(second.financials["revenue_usd"])


def test_revenue_identity_holds() -> None:
    dataset = generate_dataset()
    expected = dataset.financials["quantity"] * dataset.financials["unit_price_local"] * dataset.financials["fx_rate_to_usd"]
    deviation = (expected - dataset.financials["revenue_usd"]).abs()
    assert deviation.max() < 1.0


def test_validate_dataset_reports_no_issues() -> None:
    assert validate_dataset(generate_dataset()) == []


def test_only_the_declared_gap_is_missing() -> None:
    dataset = generate_dataset()
    missing = dataset.financials[dataset.financials.isna().any(axis=1)]
    assert len(missing) == len(DECLARED_GAPS)
    row = missing.iloc[0]
    gap = DECLARED_GAPS[0]
    assert (row["region"], row["month"], gap["column"]) == (gap["region"], gap["month"], gap["column"])
    assert pd.isna(row[gap["column"]])


def test_dataset_shape_matches_the_documented_period() -> None:
    dataset = generate_dataset()
    months = dataset.months
    assert len(months) == 24
    assert months[0] == "2023-01"
    assert months[-1] == "2024-12"
    assert sorted(dataset.financials["region"].unique().tolist()) == sorted(region.code for region in REGIONS)
    assert dataset.financials["currency"].nunique() == len(REGIONS)


def test_budget_covers_every_actual_month() -> None:
    dataset = generate_dataset()
    assert sorted(dataset.budget["month"].unique().tolist()) == dataset.months


def test_macro_fixtures_are_flagged_as_fixtures() -> None:
    dataset = generate_dataset()
    assert dataset.macro["is_fixture"].all()
    assert dataset.macro["source_url"].str.startswith("https://fred.stlouisfed.org/series/").all()
    assert dataset.macro["observation_date"].nunique() == len(dataset.months)


def test_balance_sheet_story_is_risk_relevant() -> None:
    """The demo must contain a real deterioration, not a flat line."""
    dataset = generate_dataset()
    frame = dataset.financials
    monthly = frame.groupby("month").agg(
        revenue=("revenue_usd", "sum"),
        cogs=("cogs_material_usd", "sum"),
        cash=("cash_usd", "sum"),
        ar=("accounts_receivable_usd", "sum"),
    )
    monthly["gross_margin"] = (monthly["revenue"] - monthly["cogs"]) / monthly["revenue"]
    assert monthly["gross_margin"].iloc[0] > monthly["gross_margin"].iloc[-1]
    assert monthly["cash"].iloc[-1] < monthly["cash"].iloc[0]
    assert monthly["cash"].min() > 0, "the demo company must not run out of cash"
    assert monthly["ar"].iloc[-1] > monthly["ar"].iloc[0]


def test_write_and_reload_round_trip(tmp_path) -> None:
    dataset = generate_dataset()
    manifest = write_dataset(dataset, tmp_path)
    assert set(manifest["sha256"]) == {
        "monthly_financials.csv",
        "monthly_budget.csv",
        "macro_series.csv",
        "company_profile.json",
    }
    reloaded = load_dataset(tmp_path)
    pd.testing.assert_frame_equal(reloaded.financials, dataset.financials)
    pd.testing.assert_frame_equal(reloaded.budget, dataset.budget)
    assert reloaded.profile["synthetic"] is True
    assert reloaded.manifest["seed"] == dataset.manifest["seed"]


def test_regenerating_into_the_same_directory_is_byte_identical(tmp_path) -> None:
    first = write_dataset(generate_dataset(), tmp_path)
    second = write_dataset(generate_dataset(), tmp_path)
    assert first["sha256"] == second["sha256"]


def test_shipped_seed_files_match_a_fresh_generation(seed_dataset) -> None:
    """Guards against a hand-edited CSV drifting away from the generator."""
    fresh = generate_dataset()
    pd.testing.assert_frame_equal(
        fresh.financials.reset_index(drop=True), seed_dataset.financials.reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(fresh.budget.reset_index(drop=True), seed_dataset.budget.reset_index(drop=True))


def test_validate_dataset_detects_a_broken_revenue_identity() -> None:
    dataset = generate_dataset()
    broken = dataset.financials.copy()
    broken.loc[0, "revenue_usd"] = broken.loc[0, "revenue_usd"] + 500
    patched = dataset.__class__(
        financials=broken, budget=dataset.budget, macro=dataset.macro, profile=dataset.profile, manifest=dataset.manifest
    )
    issues = validate_dataset(patched)
    assert any("revenue identity" in issue for issue in issues)


def test_validate_dataset_detects_an_undeclared_missing_value() -> None:
    dataset = generate_dataset()
    broken = dataset.financials.copy()
    broken.loc[5, "accounts_payable_usd"] = None
    patched = dataset.__class__(
        financials=broken, budget=dataset.budget, macro=dataset.macro, profile=dataset.profile, manifest=dataset.manifest
    )
    issues = validate_dataset(patched)
    assert any("undeclared missing value" in issue for issue in issues)


def test_validate_dataset_detects_non_positive_fx() -> None:
    dataset = generate_dataset()
    broken = dataset.financials.copy()
    broken.loc[3, "fx_rate_to_usd"] = 0.0
    patched = dataset.__class__(
        financials=broken, budget=dataset.budget, macro=dataset.macro, profile=dataset.profile, manifest=dataset.manifest
    )
    assert any("fx_rate_to_usd" in issue for issue in validate_dataset(patched))


@pytest.mark.parametrize("column", ["quantity", "unit_price_local", "fx_rate_to_usd"])
def test_required_columns_are_present(column: str) -> None:
    dataset = generate_dataset()
    assert column in dataset.financials.columns
    assert dataset.financials[column].notna().all()
