"""Curated macro series the risk desk actually uses, with the reason why."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    series_id: str
    title: str
    units: str
    frequency: str
    country: str
    rationale: str
    source_url: str


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        series_id="DFF",
        title="Federal Funds Effective Rate",
        units="Percent",
        frequency="daily",
        country="US",
        rationale="Benchmark for the floating-rate portion of group debt and for interest sensitivity.",
        source_url="https://fred.stlouisfed.org/series/DFF",
    ),
    CatalogEntry(
        series_id="DGS10",
        title="10-Year Treasury Constant Maturity Rate",
        units="Percent",
        frequency="daily",
        country="US",
        rationale="Long-end reference used when discussing refinancing cost.",
        source_url="https://fred.stlouisfed.org/series/DGS10",
    ),
    CatalogEntry(
        series_id="CPIAUCSL",
        title="Consumer Price Index (All Urban Consumers, All Items)",
        units="Index 1982-1984=100",
        frequency="monthly",
        country="US",
        rationale="Demand-side price environment for pricing-power discussions.",
        source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
    ),
    CatalogEntry(
        series_id="PPIACO",
        title="Producer Price Index by Commodity: All Commodities",
        units="Index 1982=100",
        frequency="monthly",
        country="US",
        rationale="Input-cost proxy behind the material-cost driver in the scenario engine.",
        source_url="https://fred.stlouisfed.org/series/PPIACO",
    ),
    CatalogEntry(
        series_id="DTWEXBGS",
        title="Nominal Broad U.S. Dollar Index",
        units="Index Jan 2006=100",
        frequency="daily",
        country="US",
        rationale="Broad USD strength; moves the translated value of non-USD revenue.",
        source_url="https://fred.stlouisfed.org/series/DTWEXBGS",
    ),
    CatalogEntry(
        series_id="DEXTHUS",
        title="Thai Baht to One U.S. Dollar",
        units="Thai Baht to One U.S. Dollar",
        frequency="daily",
        country="TH",
        rationale="Translation exposure of the Thailand business.",
        source_url="https://fred.stlouisfed.org/series/DEXTHUS",
    ),
    CatalogEntry(
        series_id="DEXSIUS",
        title="Singapore Dollars to One U.S. Dollar",
        units="Singapore Dollars to One U.S. Dollar",
        frequency="daily",
        country="SG",
        rationale="Translation exposure of the Singapore business and HQ costs.",
        source_url="https://fred.stlouisfed.org/series/DEXSIUS",
    ),
)

CATALOG_BY_ID = {entry.series_id: entry for entry in CATALOG}
