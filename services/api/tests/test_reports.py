"""Report builder and pre-export verification tests."""

from __future__ import annotations

import pytest

from app.reports.generator import money, pct, ratio, render_html
from app.reports.verify import Citation, extract_citations, extract_numbers, overall_status, verify_report


def test_report_contains_every_required_section(report_builder) -> None:
    document = report_builder.build()
    for heading in (
        "1. Executive Summary",
        "2. KPI Performance",
        "3. Budget Performance",
        "4. External Market Signals",
        "5. Scenario Comparison",
        "6. Key Risks",
        "7. Recommended Actions",
        "8. Assumptions & Sources",
    ):
        assert f"## {heading}" in document.markdown, heading
    assert document.verification_status in {"pass", "warn"}


def test_report_passes_pre_export_verification(report_builder) -> None:
    document = report_builder.build()
    failing = [item for item in document.verification if item.status == "fail"]
    assert failing == [], [item.detail for item in failing]
    checks = {item.check_id: item for item in document.verification}
    assert len(checks) == 7
    assert checks["V-01"].status == "pass"
    assert checks["V-02"].status == "pass"
    assert checks["V-04"].status == "pass"
    assert checks["V-05"].status == "pass"
    assert checks["V-08"].status == "pass"
    # V-07 warns because the demo ships fixtures unless FRED_API_KEY is configured.
    assert checks["V-07"].status in {"pass", "warn"}


def test_report_is_labelled_synthetic_with_an_as_of_date(report_builder, engine) -> None:
    document = report_builder.build()
    assert "SYNTHETIC" in document.markdown.upper()
    assert document.as_of == engine.as_of
    assert document.as_of in document.markdown
    assert document.synthetic is True
    assert "not investment advice" in document.markdown.lower() or "Not investment advice" in document.markdown


def test_every_citation_resolves_to_a_value(report_builder) -> None:
    document = report_builder.build()
    assert len(document.citations) > 30
    registry = report_builder.registry
    assert set(document.citations) == set(registry)
    for citation_id, citation in registry.items():
        assert citation.label
        assert citation.period
        if citation.value is not None:
            assert isinstance(citation.value, float)


def test_report_is_persisted_for_download(report_builder, settings) -> None:
    document = report_builder.build()
    base = settings.runtime_dir / "reports"
    assert (base / f"{document.report_id}.md").exists()
    assert (base / f"{document.report_id}.html").exists()
    assert (base / f"{document.report_id}.verification.json").exists()


# ----------------------------------------------------------------------
# the verifier itself: it must catch tampering
# ----------------------------------------------------------------------
def test_verifier_catches_a_tampered_number() -> None:
    citation = Citation("metric:revenue@2024-12", "Revenue", 1000.0, "USD", "2024-12", ["actual:x@2024-12"])
    registry = {citation.citation_id: citation}
    good = "Revenue was 1,000 [metric:revenue@2024-12]."
    assert verify_report(good, registry, synthetic=False, as_of="2024-12")[1].status == "pass"

    tampered = "Revenue was 999,999 [metric:revenue@2024-12]."
    items = verify_report(tampered, registry, synthetic=False, as_of="2024-12")
    traceability = next(item for item in items if item.check_id == "V-02")
    assert traceability.status == "fail"
    assert "999,999" in traceability.detail


def test_verifier_catches_an_uncited_figure() -> None:
    registry: dict[str, Citation] = {}
    markdown = "Revenue was 1,234,567 without any citation."
    items = verify_report(markdown, registry, synthetic=False, as_of="2024-12")
    coverage = next(item for item in items if item.check_id == "V-04")
    assert coverage.status == "fail"


def test_verifier_catches_an_unresolved_citation() -> None:
    markdown = "Revenue was 1,000 [metric:revenue@2024-12]."
    items = verify_report(markdown, {}, synthetic=False, as_of="2024-12")
    assert next(item for item in items if item.check_id == "V-01").status == "fail"


def test_verifier_catches_a_missing_synthetic_declaration() -> None:
    markdown = "A report with no declaration. [metric:revenue@2024-12] 1,000"
    registry = {"metric:revenue@2024-12": Citation("metric:revenue@2024-12", "Revenue", 1000.0, "USD", "2024-12")}
    items = verify_report(markdown, registry, synthetic=True, as_of="2024-12")
    assert next(item for item in items if item.check_id == "V-05").status == "fail"


def test_verifier_catches_an_undefined_metric_shown_as_a_value() -> None:
    registry = {"metric:gross_margin@2024-12": Citation("metric:gross_margin@2024-12", "GM", None, "pct", "2024-12")}
    markdown = "SYNTHETIC. As-of 2024-12. gross_margin = 0.4 [metric:gross_margin@2024-12]"
    items = verify_report(
        markdown, registry, synthetic=True, as_of="2024-12", undefined_metrics=["gross_margin"]
    )
    assert next(item for item in items if item.check_id == "V-08").status == "fail"


def test_verifier_warns_on_fixture_market_data() -> None:
    markdown = "SYNTHETIC as-of 2024-12"
    items = verify_report(
        markdown, {}, synthetic=True, as_of="2024-12", market_notes=["DFF: local demo fixture (NOT live data)"]
    )
    assert next(item for item in items if item.check_id == "V-07").status == "warn"


def test_overall_status_precedence() -> None:
    from app.schemas import VerificationItem

    def item(status: str):
        return VerificationItem(check_id="V-01", description="d", status=status, detail="")

    assert overall_status([item("pass"), item("pass")]) == "pass"
    assert overall_status([item("pass"), item("warn")]) == "warn"
    assert overall_status([item("warn"), item("fail")]) == "fail"


def test_number_and_citation_extraction_ignores_periods() -> None:
    assert extract_citations("x [metric:revenue@2024-12] y [risk:RC-06@2024-12]") == [
        "metric:revenue@2024-12",
        "risk:RC-06@2024-12",
    ]
    assert extract_numbers("period 2024-12 costs 1,234,567 and 22% and 15.0 days") == [
        "1,234,567",
        "22%",
        "15.0 days",
    ]
    assert extract_numbers("plain 2024 and 2024-12") == []


def test_citation_format_options() -> None:
    pct_citation = Citation("metric:gross_margin@2024-12", "GM", 0.2193, "pct", "2024-12")
    assert "21.9%" in pct_citation.formats()
    assert "22%" in pct_citation.formats()
    days_citation = Citation("metric:dso@2024-12", "DSO", 69.42, "days", "2024-12")
    assert "69.4 days" in days_citation.formats()
    percent_points = Citation("series:DFF@2024-12-01", "DFF", 4.83, "percent_points", "2024-12-01")
    assert "4.83%" in percent_points.formats()
    signed = Citation("risk:RC-11@2024-12", "EBIT variance", -0.5334, "pct", "2024-12")
    assert "-53.3%" in signed.formats()
    assert "53.3%" in signed.formats(), "a decline of 53% is the same evidence as -53%"


def test_formatters_never_invent_a_value() -> None:
    assert money(None) == "n/a"
    assert pct(None) == "n/a"
    assert ratio(None) == "n/a"
    assert money(1234.5) == "1,234"
    assert pct(0.2193) == "21.9%"


def test_html_renderer_handles_tables_lists_and_escapes_html() -> None:
    html = render_html(
        "# Title\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n- bullet\n\n<script>alert(1)</script>",
        "t",
    )
    assert "<h1>Title</h1>" in html
    assert "<table>" in html and "<th>A</th>" in html
    assert "<li>bullet</li>" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_report_for_a_dataset_without_a_budget_says_so(engine, scenario_engine, market_adapter, risk_engine, settings) -> None:
    from app.reports.generator import ReportBuilder

    patched = engine.dataset.__class__(
        financials=engine.dataset.financials,
        budget=engine.dataset.budget.iloc[0:0],
        macro=engine.dataset.macro,
        profile=engine.dataset.profile,
        manifest=engine.dataset.manifest,
    )
    empty_engine = engine.__class__(patched)
    builder = ReportBuilder(empty_engine, scenario_engine, market_adapter, risk_engine, settings)
    document = builder.build()
    assert "No budget layer is available" in document.markdown
    assert document.verification_status in {"pass", "warn"}
