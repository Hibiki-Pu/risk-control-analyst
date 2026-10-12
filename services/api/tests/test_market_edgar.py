"""SEC EDGAR connector tests: the design exists, and it refuses to pretend."""

from __future__ import annotations

import pytest

from app.core.config import EdgarSettings
from app.market.edgar import (
    ACCESS_POLICY,
    ENDPOINTS,
    IMPLEMENTED,
    EdgarAdapter,
    EdgarMisconfigured,
    EdgarNotEnabled,
)


def test_v1_ships_a_designed_but_disabled_connector() -> None:
    assert IMPLEMENTED is False
    adapter = EdgarAdapter()
    status = adapter.status()
    assert status["implemented"] is False
    assert status["available"] is False
    assert "designed but not implemented in v1" in status["reason"]


def test_the_design_documents_endpoints_and_access_policy() -> None:
    status = EdgarAdapter().status()
    assert len(status["endpoints"]) >= 4
    templates = " ".join(endpoint["url_template"] for endpoint in status["endpoints"])
    for expected in ("data.sec.gov/submissions", "companyconcept", "company_tickers.json", "browse-edgar"):
        assert expected in templates, expected
    assert len(status["access_policy"]) >= 4
    assert any("User-Agent" in rule for rule in ACCESS_POLICY)
    assert any("10 requests per second" in rule for rule in ACCESS_POLICY)
    assert status["planned_models"] == ["EdgarFiling", "EdgarFact"]


def test_settings_default_to_off_and_unconfigured() -> None:
    settings = EdgarSettings()
    assert settings.enabled is False
    assert settings.configured is False
    assert settings.min_request_interval_seconds >= 0.1, "must stay under the SEC fair-access rate limit"
    assert settings.cache_ttl_seconds >= 3600


def test_enabling_without_a_user_agent_reports_that_specifically() -> None:
    adapter = EdgarAdapter(EdgarSettings(enabled=True, user_agent=""))
    status = adapter.status()
    assert status["enabled"] is True
    assert status["configured"] is False
    assert status["available"] is False
    # v1 refuses before the configuration question is even reached.
    assert status["implemented"] is False


def test_configured_status_message_would_be_accurate_when_implemented() -> None:
    """Guard the branch that a future implementation will rely on."""
    import app.market.edgar as edgar

    adapter = EdgarAdapter(EdgarSettings(enabled=True, user_agent="RiskControl Analyst demo (contact@example.invalid)"))
    original = edgar.IMPLEMENTED
    try:
        edgar.IMPLEMENTED = True
        status = adapter.status()
        assert status["implemented"] is True
        assert status["available"] is True
        assert status["reason"] == "The connector is enabled and configured."
    finally:
        edgar.IMPLEMENTED = original


def test_every_fetch_method_refuses_with_a_reason() -> None:
    adapter = EdgarAdapter()
    for call in (
        lambda: adapter.resolve_cik("AAPL"),
        lambda: adapter.list_filings("0000320193"),
        lambda: adapter.get_company_concept("0000320193", "Revenues"),
    ):
        with pytest.raises(EdgarNotEnabled) as excinfo:
            call()
        assert "docs/market-data-sources.md" in str(excinfo.value)


def test_disabled_switch_refuses_before_any_request() -> None:
    import app.market.edgar as edgar

    original = edgar.IMPLEMENTED
    try:
        edgar.IMPLEMENTED = True
        adapter = EdgarAdapter(EdgarSettings(enabled=False, user_agent="someone@example.invalid"))
        with pytest.raises(EdgarNotEnabled):
            adapter.list_filings("0000320193")
        configured = EdgarAdapter(EdgarSettings(enabled=True, user_agent=""))
        with pytest.raises(EdgarMisconfigured):
            configured.resolve_cik("AAPL")
    finally:
        edgar.IMPLEMENTED = original


def test_status_endpoint_is_exposed(client) -> None:
    response = client.get("/api/v1/market/edgar/status")
    assert response.status_code == 200
    body = response.json()
    assert body["implemented"] is False
    assert body["available"] is False
    assert "SEC EDGAR connector is designed but not implemented" in body["reason"]
    assert {endpoint["method"] for endpoint in body["endpoints"]} == {"GET"}


def test_edgar_is_not_reachable_through_the_agent_tool_set() -> None:
    """A future EDGAR integration must add an explicit tool, not reuse another."""
    from app.agent.tools import TOOLS

    assert not any("edgar" in name.lower() for name in TOOLS)
