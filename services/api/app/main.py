"""FastAPI application entry point.

Run locally:
    python -m uvicorn app.main:app --reload --port 8000   # from services/api
or  uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.services import get_services

logger = logging.getLogger("riskcontrol.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_runtime_dir()
    services = get_services()
    try:
        services.store.ensure_seed()
        services.bundle()
        logger.info("RiskControl Analyst API ready; dataset=%s", services.store.active().dataset_id)
    except FileNotFoundError as exc:
        logger.warning("Seed data unavailable: %s", exc)
    yield


app = FastAPI(
    title="RiskControl Analyst API",
    version="0.1.0",
    description=(
        "Deterministic financial and risk-control calculations for the RiskControl Analyst demo.\n\n"
        "Every response carries units, period and source ids. Market data is live FRED only when a key is "
        "configured; otherwise clearly-labelled local fixtures are served. All shipped data is SYNTHETIC."
    ),
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": "RiskControl Analyst API",
        "docs": "/docs",
        "api": "/api/v1",
        "data_notice": "SYNTHETIC demo data only. Not investment advice.",
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a useful message without leaking stack traces or configuration."""
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
            "path": request.url.path,
            "hint": "Check the server log. No stack trace or secret is returned to the client.",
        },
    )
