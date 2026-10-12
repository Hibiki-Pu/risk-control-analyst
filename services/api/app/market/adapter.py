"""Market Data Adapter.

Rules enforced here:

* **Never invent a value.** If FRED is not configured or unreachable, the
  adapter serves the local fixture and says so through ``is_fixture`` and
  ``error`` — it never presents a fixture as a live observation.
* **Cache, timeout, retry, rate limit.** Live calls respect a minimum interval,
  a request timeout, bounded exponential-backoff retries and an on-disk cache
  with a TTL.
* **No blind alignment.** Series keep their native frequency and the response
  states the latest observation date plus an alignment note. Nothing is
  forward-filled across frequencies.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

from app.core.config import FredSettings, Settings, get_fred_settings, get_settings
from app.market.catalog import CATALOG, CATALOG_BY_ID, CatalogEntry
from app.schemas import MarketCatalogItem, MarketObservation, MarketSeries

FIXTURE_LICENSE = (
    "Series metadata (id, title, units, frequency, source URL) mirrors the public FRED catalogue. "
    "The numeric values served in fixture mode are hand-built DEMO values for this portfolio project "
    "and must not be used as real market data."
)

LIVE_LICENSE = (
    "Source: FRED, Federal Reserve Bank of St. Louis. Review the FRED terms of use before commercial "
    "redistribution."
)


@dataclass
class _CacheEntry:
    fetched_at: datetime
    payload: dict


class MarketDataAdapter:
    def __init__(
        self,
        macro_frame: pd.DataFrame,
        settings: Settings | None = None,
        fred: FredSettings | None = None,
        client: httpx.Client | None = None,
    ):
        self.macro = macro_frame.copy()
        self.settings = settings or get_settings()
        self.fred = fred or get_fred_settings()
        self._client = client
        self._last_request_at = 0.0
        self.cache_dir = self.settings.runtime_dir / "market_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def catalog(self) -> list[MarketCatalogItem]:
        available = set(self.macro["series_id"].unique().tolist()) if not self.macro.empty else set()
        return [
            MarketCatalogItem(
                series_id=entry.series_id,
                title=entry.title,
                units=entry.units,
                frequency=entry.frequency,
                country=entry.country,
                rationale=entry.rationale,
                source_url=entry.source_url,
                available=entry.series_id in available or self.fred.configured,
            )
            for entry in CATALOG
        ]

    def get_series(self, series_id: str, allow_live: bool = True, limit: int = 60) -> MarketSeries:
        entry = CATALOG_BY_ID.get(series_id)
        if entry is None:
            return MarketSeries(
                series_id=series_id,
                title="Unknown series",
                units="n/a",
                frequency="unknown",
                fetched_at=datetime.now(timezone.utc),
                source_url="",
                error=(
                    f"Series '{series_id}' is not in the supported catalogue. "
                    "Request one of: " + ", ".join(item.series_id for item in CATALOG)
                ),
                is_fixture=True,
            )

        if allow_live and self.fred.configured:
            cached = self._read_cache(entry.series_id)
            if cached is not None:
                return cached
            try:
                series = self._fetch_live(entry, limit=limit)
                self._write_cache(series)
                return series
            except Exception as exc:  # noqa: BLE001 - surfaced to the caller verbatim
                fixture = self._fixture_series(entry)
                fixture.error = (
                    f"Live FRED request failed ({type(exc).__name__}: {exc}). "
                    "Serving the local demo fixture instead — these are NOT live values."
                )
                return fixture
        return self._fixture_series(entry)

    # ------------------------------------------------------------------
    # fixtures
    # ------------------------------------------------------------------
    def _fixture_series(self, entry: CatalogEntry) -> MarketSeries:
        subset = self.macro[self.macro["series_id"] == entry.series_id].copy()
        if subset.empty:
            return MarketSeries(
                series_id=entry.series_id,
                title=entry.title,
                units=entry.units,
                frequency=entry.frequency,  # type: ignore[arg-type]
                country=entry.country,
                source_url=entry.source_url,
                fetched_at=datetime.now(timezone.utc),
                error=f"No local fixture is shipped for {entry.series_id}.",
                is_fixture=True,
                license_note=FIXTURE_LICENSE,
            )
        subset["observation_date"] = pd.to_datetime(subset["observation_date"])
        subset = subset.sort_values("observation_date")
        observations = [
            MarketObservation(date=row["observation_date"].date(), value=float(row["value"]))
            for _, row in subset.iterrows()
        ]
        fetched_at = subset["fetched_at"].iloc[-1]
        return self._build_series(
            entry,
            observations,
            fetched_at=pd.Timestamp(fetched_at).to_pydatetime(),
            is_fixture=True,
            license_note=FIXTURE_LICENSE,
        )

    # ------------------------------------------------------------------
    # live FRED
    # ------------------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.fred.min_request_interval_seconds - elapsed
        if wait > 0:
            time.sleep(wait)

    def _fetch_live(self, entry: CatalogEntry, limit: int = 60) -> MarketSeries:
        client = self._client or httpx.Client(timeout=self.fred.timeout_seconds)
        last_error: Exception | None = None
        params = {
            "series_id": entry.series_id,
            "api_key": self.fred.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }
        for attempt in range(self.fred.max_retries + 1):
            self._throttle()
            try:
                response = client.get(f"{self.fred.base_url}/series/observations", params=params)
                self._last_request_at = time.monotonic()
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"FRED returned {response.status_code}", request=response.request, response=response
                    )
                response.raise_for_status()
                payload = response.json()
                break
            except Exception as exc:  # noqa: BLE001 - retried below
                last_error = exc
                if attempt >= self.fred.max_retries:
                    raise
                time.sleep(min(4.0, 0.5 * (2**attempt)))
        else:  # pragma: no cover - defensive, the loop either breaks or raises
            raise last_error or RuntimeError("FRED request failed")

        observations: list[MarketObservation] = []
        for item in payload.get("observations", []):
            raw = item.get("value")
            value = None if raw in (None, ".") else float(raw)
            observations.append(MarketObservation(date=date.fromisoformat(item["date"]), value=value))
        observations.sort(key=lambda observation: observation.date)
        if not observations:
            raise ValueError(f"FRED returned no observations for {entry.series_id}")

        return self._build_series(
            entry,
            observations,
            fetched_at=datetime.now(timezone.utc),
            is_fixture=False,
            license_note=LIVE_LICENSE,
        )

    # ------------------------------------------------------------------
    def _build_series(
        self,
        entry: CatalogEntry,
        observations: list[MarketObservation],
        *,
        fetched_at: datetime,
        is_fixture: bool,
        license_note: str,
    ) -> MarketSeries:
        dated = [observation for observation in observations if observation.value is not None]
        latest = dated[-1] if dated else None
        previous = dated[-2] if len(dated) > 1 else None
        stale_cutoff = datetime.now(timezone.utc).date() - timedelta(days=self.settings.stale_market_data_days)
        is_stale = bool(latest and latest.date < stale_cutoff) if not is_fixture else False
        alignment = (
            f"Native frequency: {entry.frequency}. No forward-fill or cross-frequency alignment is applied; "
            "consumers must join on the observation date they actually need."
        )
        if is_fixture:
            alignment += " Fixture coverage ends with the synthetic dataset period."
            is_stale = False
        return MarketSeries(
            series_id=entry.series_id,
            title=entry.title,
            units=entry.units,
            frequency=entry.frequency,  # type: ignore[arg-type]
            country=entry.country,
            source_name="FRED (Federal Reserve Bank of St. Louis)" if not is_fixture else "Local demo fixture",
            source_url=entry.source_url,
            fetched_at=fetched_at,
            latest_observation_date=latest.date if latest else None,
            latest_value=latest.value if latest else None,
            previous_value=previous.value if previous else None,
            change=(latest.value - previous.value) if latest and previous else None,
            observations=observations,
            is_fixture=is_fixture,
            is_stale=is_stale,
            stale_after_days=self.settings.stale_market_data_days,
            alignment_note=alignment,
            license_note=license_note,
        )

    # ------------------------------------------------------------------
    # cache
    # ------------------------------------------------------------------
    def _cache_path(self, series_id: str) -> Path:
        return self.cache_dir / f"{series_id}.json"

    def _read_cache(self, series_id: str) -> MarketSeries | None:
        path = self._cache_path(series_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            if datetime.now(timezone.utc) - fetched_at > timedelta(seconds=self.fred.cache_ttl_seconds):
                return None
            series = MarketSeries.model_validate(payload["series"])
            series.alignment_note = series.alignment_note or "Served from the local FRED cache."
            return series
        except Exception:  # noqa: BLE001 - a corrupt cache must never break the request
            return None

    def _write_cache(self, series: MarketSeries) -> None:
        payload = {"fetched_at": series.fetched_at.isoformat(), "series": series.model_dump(mode="json")}
        self._cache_path(series.series_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def provenance_summary(series: MarketSeries) -> str:
    """One-line provenance string used in reports and the API."""
    origin = "local demo fixture (NOT live data)" if series.is_fixture else "FRED live observation"
    latest = series.latest_observation_date.isoformat() if series.latest_observation_date else "n/a"
    return (
        f"{series.series_id}: {origin}; units={series.units}; frequency={series.frequency}; "
        f"latest={latest}; fetched_at={series.fetched_at.isoformat()}; source={series.source_url}"
    )
