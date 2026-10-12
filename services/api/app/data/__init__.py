"""Synthetic demo dataset — the ONLY data shape shipped with the repo."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SyntheticDataset:
    """Container for the generated demo dataset."""

    financials: pd.DataFrame
    budget: pd.DataFrame
    macro: pd.DataFrame
    profile: dict
    manifest: dict

    @property
    def months(self) -> list[str]:
        return sorted(self.financials["month"].unique().tolist())
