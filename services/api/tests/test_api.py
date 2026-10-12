"""HTTP contract tests (FastAPI TestClient)."""

from __future__ import annotations

import io
import json

import pandas as pd
import pytest

from tests.helpers import build_tiny_dataset


def test_health_reports_dataset_and_disclaimer(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dataset"]["synthetic"] is True
    assert body["dataset"]["months"][0] == "2023-01"
    assert body["dataset"]["has_budget_layer"] is True
    assert "Not investment advice" in body["disclaimer"]


def test_root_and_openapi(client) -> None:
    assert client.get("/").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/v1/metrics" in schema["paths"]


def test_company_and_lineage(client) -> None:
    company = client.get("/api/v1/meta/company").json()
    assert company["profile"]["synthetic"] is True
    assert company["seed_manifest"]["seed"] == 20260101
    lineage = client.get("/api/v1/meta/lineage").json()["lineage"]
    assert len(lineage) == 3
    assert all(item["synthetic"] for item in lineage)


def test_metrics_endpoint_returns_cited_values(client) -> None:
    body = client.get("/api/v1/metrics", params={"month": "2024-12"}).json()
    assert body["period"] == "2024-12"
    revenue = body["values"]["revenue"]
    assert revenue["unit"] == "USD"
    assert revenue["status"] == "ok"
    assert revenue["source_ids"] == ["actual:monthly_financials@2024-12"]
    assert revenue["value"] == pytest.approx(322304.71, abs=0.5)
    assert body["values"]["cash"]["value"] == pytest.approx(274200.03, abs=1.0)


def test_metrics_range_and_region_filter(client) -> None:
    body = client.get(
        "/api/v1/metrics", params=[("start", "2024-01"), ("end", "2024-12"), ("regions", "SG"), ("regions", "TH")]
    ).json()
    assert body["period"] == "2024-01..2024-12"
    assert body["scope"]["regions"] == ["SG", "TH"]
    assert body["values"]["revenue"]["value"] < 3706443.02


def test_metrics_rejects_a_bad_month(client) -> None:
    assert client.get("/api/v1/metrics", params={"month": "2024-13"}).status_code == 422
    single = client.get("/api/v1/metrics", params={"month": "2019-01"})
    assert single.status_code == 400
    assert "no data in the requested period" in single.json()["detail"]
    ranged = client.get("/api/v1/metrics", params={"start": "2019-01", "end": "2019-06"})
    assert ranged.status_code == 400
    assert "no months in range" in ranged.json()["detail"]


def test_series_endpoint(client) -> None:
    body = client.get("/api/v1/metrics/series", params={"limit": 6}).json()
    assert len(body["points"]) == 6
    point = body["points"][-1]
    assert point["month"] == "2024-12"
    assert point["gross_margin_pct"] is not None
    assert point["budget_revenue_usd"] is not None


def test_budget_variance_endpoint(client) -> None:
    body = client.get("/api/v1/metrics/budget-variance", params={"month": "2024-12"}).json()
    assert body["values"]["revenue_variance"]["basis"] == "variance"
    assert body["values"]["revenue_variance_pct"]["unit"] == "pct"


def test_risk_register_endpoint(client) -> None:
    body = client.get("/api/v1/risk/register").json()
    assert body["overall_level"] in {"high", "critical"}
    assert body["score"] > 0
    signal = body["signals"][0]
    assert signal["severity"] in {"critical", "high"}
    assert signal["synthetic"] is True
    assert body["data_gaps"]


def test_market_endpoints(client) -> None:
    catalog = client.get("/api/v1/market/catalog").json()
    assert catalog["fred_configured"] is False
    assert any(item["series_id"] == "DFF" for item in catalog["series"])
    assert "never presented as live" in catalog["policy"]
    series = client.get("/api/v1/market/series/DFF").json()
    assert series["is_fixture"] is True
    assert series["latest_value"] is not None
    assert client.get("/api/v1/market/series/NOPE").status_code == 404


def test_scenario_presets_and_run(client) -> None:
    presets = client.get("/api/v1/scenarios/presets").json()["presets"]
    assert {item["scenario_id"] for item in presets} == {"base", "upside", "downside"}
    body = client.post(
        "/api/v1/scenarios/run",
        json={"assumptions": {"horizon_months": 6, "price_change_pct": 0.03}, "label": "Pricing test"},
    ).json()
    assert body["horizon_months"] == 6
    assert {summary["scenario_id"] for summary in body["scenarios"]} == {"base", "upside", "downside", "custom"}
    assert body["sensitivities"]
    custom = next(summary for summary in body["scenarios"] if summary["scenario_id"] == "custom")
    assert custom["label"] == "Pricing test"
    assert custom["ebit_usd"] > body["baseline"]["ebit_usd"]


def test_scenario_run_rejects_unknown_fields(client) -> None:
    response = client.post("/api/v1/scenarios/run", json={"assumptions": {"horizon_months": 6, "tax_hack": 0.0}})
    assert response.status_code == 422


def test_scenario_export_returns_csv(client) -> None:
    response = client.post("/api/v1/scenarios/export", json={"assumptions": {"horizon_months": 3}})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("scenario_id,month")
    assert len(lines) == 1 + 3 * 4


def test_agent_tools_and_ask_and_audit(client) -> None:
    tools = client.get("/api/v1/agent/tools").json()["tools"]
    assert {item["name"] for item in tools} >= {"get_financial_metrics", "get_risk_signals", "run_scenario"}
    answer = client.post("/api/v1/agent/ask", json={"question": "我们的风险状况如何？", "month": "2024-12"}).json()
    assert answer["engine"] == "deterministic-planner"
    assert answer["key_findings"]
    assert answer["evidence"]
    assert all(record["status"] == "ok" for record in answer["tool_calls"])
    audit = client.get("/api/v1/agent/audit", params={"limit": 5}).json()
    assert audit["count"] >= len(answer["tool_calls"])
    assert "never stored" in audit["note"]


def test_agent_ask_validates_the_question(client) -> None:
    assert client.post("/api/v1/agent/ask", json={"question": "x"}).status_code == 422
    assert client.post("/api/v1/agent/ask", json={"question": "hello", "extra": 1}).status_code == 422


def test_report_generation_and_download(client) -> None:
    document = client.post("/api/v1/reports/generate", json={"horizon_months": 6}).json()
    assert document["verification_status"] in {"pass", "warn"}
    assert {item["check_id"] for item in document["verification"]} == {
        "V-01",
        "V-02",
        "V-04",
        "V-05",
        "V-06",
        "V-07",
        "V-08",
    }
    report_id = document["report_id"]
    markdown = client.get(f"/api/v1/reports/{report_id}", params={"format": "markdown"})
    assert markdown.status_code == 200
    assert markdown.text.startswith("# Risk Control & Financial Performance Report")
    html = client.get(f"/api/v1/reports/{report_id}", params={"format": "html"})
    assert "<table>" in html.text
    payload = client.get(f"/api/v1/reports/{report_id}", params={"format": "json"}).json()
    assert payload["report_id"] == report_id
    assert client.get("/api/v1/reports/DOES-NOT-EXIST").status_code == 404
    assert client.get(f"/api/v1/reports/{report_id}", params={"format": "pdf"}).status_code == 422


def test_upload_validates_then_activates_and_can_be_reverted(client) -> None:
    tiny = build_tiny_dataset()
    buffer = io.StringIO()
    tiny.financials.to_csv(buffer, index=False)

    record = client.post(
        "/api/v1/data/upload",
        files={"file": ("tiny.csv", buffer.getvalue(), "text/csv")},
    ).json()
    assert record["report"]["passed"] is True
    assert record["activated"] is True

    health = client.get("/api/v1/health").json()
    assert health["dataset"]["kind"] == "uploaded_file"
    assert health["dataset"]["synthetic"] is False
    assert health["dataset"]["has_budget_layer"] is False

    metrics = client.get("/api/v1/metrics", params={"month": "2024-01"}).json()
    assert metrics["values"]["revenue"]["value"] == pytest.approx(500.0)

    variance = client.get("/api/v1/metrics/budget-variance", params={"month": "2024-01"}).json()
    assert variance["values"]["revenue_variance"]["status"] == "missing"
    assert "No budget layer" in variance["values"]["revenue_variance"]["note"]

    uploads = client.get("/api/v1/data/uploads").json()["uploads"]
    assert uploads and uploads[0]["upload_id"] == record["upload_id"]

    restored = client.post("/api/v1/data/activate-seed").json()
    assert restored["kind"] == "synthetic_seed"
    assert len(client.get("/api/v1/health").json()["dataset"]["months"]) == 24


def test_upload_rejects_an_invalid_file(client) -> None:
    buffer = io.StringIO()
    pd.DataFrame({"month": ["2024-01"], "region": ["SG"], "currency": ["SGD"], "quantity": [1]}).to_csv(
        buffer, index=False
    )
    record = client.post(
        "/api/v1/data/upload", files={"file": ("broken.csv", buffer.getvalue(), "text/csv")}
    ).json()
    assert record["report"]["passed"] is False
    assert record["activated"] is False
    assert record["report"]["missing_required"]
    # The active dataset is untouched by a failed upload.
    assert client.get("/api/v1/health").json()["dataset"]["kind"] == "synthetic_seed"


def test_upload_rejects_duplicate_rows(client) -> None:
    tiny = build_tiny_dataset()
    duplicated = pd.concat([tiny.financials, tiny.financials], ignore_index=True)
    buffer = io.StringIO()
    duplicated.to_csv(buffer, index=False)
    record = client.post(
        "/api/v1/data/upload", files={"file": ("dupes.csv", buffer.getvalue(), "text/csv")}
    ).json()
    assert record["report"]["passed"] is False
    assert any("duplicate" in issue["message"] for issue in record["report"]["issues"])


def test_upload_rejects_an_empty_file(client) -> None:
    response = client.post("/api/v1/data/upload", files={"file": ("empty.csv", "", "text/csv")})
    assert response.status_code == 400


def test_upload_repairs_a_broken_revenue_identity_with_a_warning(client) -> None:
    tiny = build_tiny_dataset()
    frame = tiny.financials.copy()
    frame.loc[0, "revenue_usd"] = 99999.0
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    record = client.post(
        "/api/v1/data/upload", files={"file": ("mismatch.csv", buffer.getvalue(), "text/csv")}
    ).json()
    assert record["report"]["passed"] is True
    assert any("does not equal" in issue["message"] for issue in record["report"]["issues"])
    assert record["activated"] is True
    client.post("/api/v1/data/activate-seed")


def test_errors_are_json_and_do_not_leak_paths(client) -> None:
    response = client.get("/api/v1/metrics", params={"month": "2019-01"})
    assert response.headers["content-type"].startswith("application/json")
    detail = response.json()["detail"]
    assert "Traceback" not in detail
    assert "C:\\" not in detail and "D:\\" not in detail
