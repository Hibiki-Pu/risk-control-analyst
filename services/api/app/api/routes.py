"""REST endpoints (prefix ``/api/v1``)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from app.agent.tools import describe_tools
from app.finance.scenarios import PRESETS
from app.schemas import ScenarioAssumptions
from app.services import get_services

router = APIRouter(prefix="/api/v1")


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumptions: ScenarioAssumptions = Field(default_factory=ScenarioAssumptions)
    include_presets: bool = True
    label: str = Field(default="Custom scenario", max_length=80)


class AgentQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=1000)
    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    horizon_months: int = Field(default=12, ge=1, le=36)


@router.get("/health", summary="Liveness plus dataset identity")
def health() -> dict:
    services = get_services()
    bundle = services.bundle()
    return {
        "status": "ok",
        "version": "0.1.0",
        "dataset": services.store.manifest(),
        "as_of": bundle.engine.as_of,
        "synthetic": bundle.synthetic,
        "disclaimer": "Synthetic demo data. Not investment advice.",
    }


@router.get("/meta/company", summary="Company profile of the active dataset")
def company() -> dict:
    services = get_services()
    active = services.store.active()
    return {
        "profile": active.dataset.profile,
        "dataset_id": active.dataset_id,
        "kind": active.kind,
        "synthetic": active.synthetic,
        "seed_manifest": services.store.seed_manifest(),
    }


@router.get("/meta/lineage", summary="Data lineage for every dataset in play")
def lineage() -> dict:
    bundle = get_services().bundle()
    return {"lineage": [item.model_dump(mode="json") for item in bundle.engine.lineage()]}


@router.get("/metrics", summary="Metric pack for a month or a range")
def metrics(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    start: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    end: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    regions: Annotated[list[str] | None, Query()] = None,
) -> dict:
    bundle = get_services().bundle()
    months = [month] if month else None
    try:
        pack = bundle.engine.metrics(start=start, end=end, regions=regions, months=months)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return pack.model_dump(mode="json")


@router.get("/metrics/series", summary="Monthly series for charts")
def series(
    start: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    end: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    regions: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=72)] = 24,
) -> dict:
    bundle = get_services().bundle()
    try:
        months = bundle.engine.select_months(start, end, limit=limit)
        pack = bundle.engine.series(regions=regions, months=months)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return pack.model_dump(mode="json")


@router.get("/metrics/budget-variance", summary="Actual versus plan variances")
def budget_variance(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    start: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    end: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> dict:
    bundle = get_services().bundle()
    try:
        months = [month] if month else None
        pack = bundle.engine.budget_variance(start=start, end=end, months=months)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return pack.model_dump(mode="json")


@router.get("/risk/register", summary="Rule-based risk register")
def risk_register(
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    regions: Annotated[list[str] | None, Query()] = None,
) -> dict:
    bundle = get_services().bundle()
    try:
        register = bundle.risk.build(month=month, regions=regions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return register.model_dump(mode="json")


@router.get("/market/catalog", summary="Supported macro series and why they matter")
def market_catalog() -> dict:
    bundle = get_services().bundle()
    return {
        "series": [item.model_dump(mode="json") for item in bundle.market.catalog()],
        "fred_configured": bundle.market.fred.configured,
        "policy": (
            "Live FRED values are served only when FRED_API_KEY is set. Otherwise local fixtures are served and "
            "marked is_fixture=true. Fixtures are never presented as live observations."
        ),
    }


@router.get("/market/series/{series_id}", summary="One macro series with provenance")
def market_series(
    series_id: str,
    allow_live: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=1000)] = 60,
) -> dict:
    bundle = get_services().bundle()
    series_obj = bundle.market.get_series(series_id, allow_live=allow_live, limit=limit)
    if series_obj.error and series_obj.latest_value is None:
        raise HTTPException(status_code=404, detail=series_obj.error)
    return series_obj.model_dump(mode="json")


@router.get("/scenarios/presets", summary="Preset scenario definitions")
def scenario_presets() -> dict:
    return {
        "presets": [
            {
                "scenario_id": definition.scenario_id,
                "label": definition.label,
                "description": definition.description,
                "assumptions": definition.assumptions.model_dump(),
            }
            for definition in PRESETS.values()
        ]
    }


@router.post("/scenarios/run", summary="Run base / upside / downside plus a custom case")
def run_scenarios(request: ScenarioRequest) -> dict:
    bundle = get_services().bundle()
    result = bundle.scenarios.run(
        assumptions=request.assumptions,
        include_presets=request.include_presets,
        label=request.label,
    )
    return result.model_dump(mode="json")


@router.post("/scenarios/export", summary="CSV export of every scenario month", response_class=PlainTextResponse)
def export_scenarios(request: ScenarioRequest) -> PlainTextResponse:
    bundle = get_services().bundle()
    result = bundle.scenarios.run(
        assumptions=request.assumptions, include_presets=request.include_presets, label=request.label
    )
    csv_text = bundle.scenarios.to_csv(result)
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="scenarios.csv"'},
    )


@router.get("/agent/tools", summary="The closed tool set the AI Analyst may call")
def agent_tools() -> dict:
    return {"tools": describe_tools()}


@router.post("/agent/ask", summary="Ask the AI Analyst (deterministic planner by default)")
def agent_ask(request: AgentQuestion) -> dict:
    bundle = get_services().bundle()
    answer = bundle.agent.ask(request.question, month=request.month)
    return answer.model_dump(mode="json")


@router.get("/agent/audit", summary="Recent tool-call audit log")
def agent_audit(limit: Annotated[int, Query(ge=1, le=200)] = 20) -> dict:
    bundle = get_services().bundle()
    records = bundle.agent.audit[-limit:]
    return {
        "count": len(bundle.agent.audit),
        "records": [record.model_dump(mode="json") for record in records],
        "note": "Arguments and timings only. Prompts, secrets and personal data are never stored.",
    }


@router.post("/reports/generate", summary="Build the management report and verify it")
def generate_report(request: ReportRequest) -> dict:
    bundle = get_services().bundle()
    try:
        document = bundle.reports.build(month=request.month, horizon_months=request.horizon_months)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return document.model_dump(mode="json")


@router.get("/reports/{report_id}", summary="Fetch a generated report", response_model=None)
def get_report(
    report_id: str,
    format: Annotated[str, Query(pattern="^(markdown|html|json)$")] = "markdown",
) -> dict | PlainTextResponse:
    services = get_services()
    target = services.settings.runtime_dir / "reports"
    suffix = {"markdown": "md", "html": "html", "json": "verification.json"}[format]
    path = target / f"{report_id}.{suffix}"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"report {report_id} not found (generate it first)")
    if format == "json":
        return {"report_id": report_id, "content": path.read_text(encoding="utf-8")}
    return PlainTextResponse(
        path.read_text(encoding="utf-8"),
        media_type="text/markdown" if format == "markdown" else "text/html",
    )


@router.post("/data/upload", summary="Upload a CSV/Excel actuals file (validated, then activated)")
def upload_dataset(file: Annotated[UploadFile, File()]) -> dict:
    services = get_services()
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file larger than 20 MB is not accepted")
    record = services.store.ingest_upload(content, file.filename or "upload.csv", activate=True)
    if record["activated"]:
        services.invalidate()
    return record


@router.post("/data/activate-seed", summary="Switch back to the shipped synthetic seed dataset")
def activate_seed() -> dict:
    services = get_services()
    services.store.activate_seed()
    services.invalidate()
    return services.store.manifest()


@router.get("/data/uploads", summary="Upload history for this process")
def list_uploads() -> dict:
    return {"uploads": get_services().store.uploads()}
