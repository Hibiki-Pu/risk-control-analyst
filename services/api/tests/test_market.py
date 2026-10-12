"""Market Data Adapter tests — provenance, caching, retries, honest fallback."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.config import FredSettings, Settings
from app.market.adapter import MarketDataAdapter, provenance_summary
from app.market.catalog import CATALOG


def _adapter(tmp_path, macro, client=None, api_key: str = "", ttl: int = 3600) -> MarketDataAdapter:
    settings = Settings(runtime_dir=tmp_path, fred_api_key=api_key)
    fred = FredSettings(
        api_key=api_key,
        cache_ttl_seconds=ttl,
        min_request_interval_seconds=0.0,
        max_retries=1,
        timeout_seconds=2.0,
    )
    return MarketDataAdapter(macro, settings=settings, fred=fred, client=client)


def test_catalog_documents_every_series() -> None:
    for entry in CATALOG:
        assert entry.series_id
        assert entry.rationale
        assert entry.source_url.startswith("https://fred.stlouisfed.org/series/")


def test_serves_labelled_fixtures_without_a_key(seed_dataset, tmp_path) -> None:
    adapter = _adapter(tmp_path, seed_dataset.macro)
    catalog = adapter.catalog()
    assert any(item.series_id == "DFF" for item in catalog)
    series = adapter.get_series("DFF")
    assert series.is_fixture is True
    assert series.source_name == "Local demo fixture"
    assert series.latest_value is not None
    assert series.latest_observation_date is not None
    assert "fixture" in provenance_summary(series).lower()
    assert "NOT live" in provenance_summary(series)
    assert series.error is None, "an expected fixture is not an error"


def test_unknown_series_returns_an_explanatory_error(seed_dataset, tmp_path) -> None:
    adapter = _adapter(tmp_path, seed_dataset.macro)
    series = adapter.get_series("NOT_A_SERIES")
    assert series.error and "supported catalogue" in series.error
    assert series.latest_value is None
    assert series.is_fixture is True


def test_fixtures_keep_native_frequency_and_never_forward_fill(seed_dataset, tmp_path) -> None:
    adapter = _adapter(tmp_path, seed_dataset.macro)
    series = adapter.get_series("CPIAUCSL")
    assert series.frequency == "monthly"
    assert "No forward-fill" in series.alignment_note
    assert len(series.observations) == len(seed_dataset.macro.query("series_id == 'CPIAUCSL'"))


def test_live_fetch_marks_provenance_as_live_and_caches(seed_dataset, tmp_path) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        assert request.url.params["series_id"] == "DFF"
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"date": "2024-11-01", "value": "4.60"},
                    {"date": "2024-12-01", "value": "4.55"},
                    {"date": "2024-12-02", "value": "."},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = _adapter(tmp_path, seed_dataset.macro, client=client, api_key="test-key")
    series = adapter.get_series("DFF")
    assert series.is_fixture is False
    assert series.latest_value == pytest.approx(4.55)
    assert series.previous_value == pytest.approx(4.60)
    assert series.change == pytest.approx(-0.05)
    assert series.source_name.startswith("FRED")
    assert calls["count"] == 1

    # Second call is served from the on-disk cache: no extra HTTP request.
    cached = adapter.get_series("DFF")
    assert calls["count"] == 1
    assert cached.latest_value == pytest.approx(4.55)
    assert cached.is_fixture is False

    cache_file = adapter.cache_dir / "DFF.json"
    assert cache_file.exists()
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["series"]["is_fixture"] is False


def test_expired_cache_triggers_a_new_request(seed_dataset, tmp_path) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"observations": [{"date": "2024-12-01", "value": "5.00"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = _adapter(tmp_path, seed_dataset.macro, client=client, api_key="k", ttl=60)
    adapter.get_series("DFF")
    assert calls["count"] == 1

    # Age the cache entry beyond the TTL instead of relying on wall-clock timing.
    cache_file = adapter.cache_dir / "DFF.json"
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["fetched_at"] = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    refreshed = adapter.get_series("DFF")
    assert calls["count"] == 2, "an expired cache entry must be refetched"
    assert refreshed.latest_value == pytest.approx(5.00)


def test_cache_is_used_within_its_ttl(seed_dataset, tmp_path) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"observations": [{"date": "2024-12-01", "value": "5.00"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = _adapter(tmp_path, seed_dataset.macro, client=client, api_key="k", ttl=600)
    adapter.get_series("DFF")
    adapter.get_series("DFF")
    assert calls["count"] == 1


def test_network_failure_falls_back_to_a_flagged_fixture(seed_dataset, tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network unreachable", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = _adapter(tmp_path, seed_dataset.macro, client=client, api_key="k")
    series = adapter.get_series("DFF")
    assert series.is_fixture is True
    assert series.error and "Live FRED request failed" in series.error
    assert series.latest_value is not None, "falling back must still serve something useful"
    assert "NOT live" in provenance_summary(series)


def test_server_error_is_retried_then_succeeds(seed_dataset, tmp_path) -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, json={"error": "temporarily unavailable"})
        return httpx.Response(200, json={"observations": [{"date": "2024-12-01", "value": "4.90"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = _adapter(tmp_path, seed_dataset.macro, client=client, api_key="k")
    series = adapter.get_series("DFF")
    assert calls["count"] == 2
    assert series.is_fixture is False
    assert series.latest_value == pytest.approx(4.90)


def test_empty_live_response_falls_back(seed_dataset, tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = _adapter(tmp_path, seed_dataset.macro, client=client, api_key="k")
    series = adapter.get_series("DFF")
    assert series.is_fixture is True
    assert series.error


def test_allow_live_false_never_calls_the_network(seed_dataset, tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not be called
        raise AssertionError("the adapter must not call FRED when allow_live is false")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = _adapter(tmp_path, seed_dataset.macro, client=client, api_key="k")
    series = adapter.get_series("DFF", allow_live=False)
    assert series.is_fixture is True


def test_corrupt_cache_is_ignored(seed_dataset, tmp_path) -> None:
    adapter = _adapter(tmp_path, seed_dataset.macro)
    adapter.cache_dir.mkdir(parents=True, exist_ok=True)
    (adapter.cache_dir / "DFF.json").write_text("{not json", encoding="utf-8")
    series = adapter.get_series("DFF")
    assert series.latest_value is not None


def test_live_values_are_marked_stale_when_old(seed_dataset, tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": [{"date": "2000-01-03", "value": "1.00"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = _adapter(tmp_path, seed_dataset.macro, client=client, api_key="k")
    series = adapter.get_series("DFF")
    assert series.is_stale is True
    assert series.stale_after_days == 120
