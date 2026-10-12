"""SEC EDGAR connector — a **designed interface that v1 deliberately does not use**.

Why it exists
-------------
The brief asks for the EDGAR interface to be designed without forcing a first
release integration. This module therefore ships:

* the data contract a future implementation must satisfy
  (:class:`EdgarFiling`, :class:`EdgarFact`, :class:`EdgarConceptSeries`),
* the exact endpoints, authentication rules and rate-limit policy the SEC
  fair-access guidance requires (see ``ENDPOINTS``),
* an explicit, testable refusal: every fetch method raises
  :class:`EdgarNotEnabled` unless the connector is both switched on **and**
  implemented, so no code path can silently present an unfinished integration as
  if it were data.

Nothing here performs network I/O in v1. ``GET /api/v1/market/edgar/status``
returns the same status object so a reviewer can see the design without reading
the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field

from app.core.config import EdgarSettings, get_edgar_settings

#: Implemented in this release? Kept as an explicit constant so the refusal
#: message, the API status and the tests all agree.
IMPLEMENTED = False


class EdgarNotEnabled(RuntimeError):
    """Raised by every fetch method while the connector is not usable."""


class EdgarMisconfigured(RuntimeError):
    """Raised when the connector is switched on without the required contact User-Agent."""


@dataclass(frozen=True)
class EdgarEndpoint:
    method: str
    url_template: str
    purpose: str
    notes: str


ENDPOINTS: tuple[EdgarEndpoint, ...] = (
    EdgarEndpoint(
        "GET",
        "https://www.sec.gov/files/company_tickers.json",
        "Resolve a ticker to a zero-padded CIK",
        "Static mapping file; cache for a day. No CIK is guessed from a company name.",
    ),
    EdgarEndpoint(
        "GET",
        "https://data.sec.gov/submissions/CIK{cik:010d}.json",
        "Company entity data and the recent filing index",
        "One request per company; the response embeds up to 1000 recent filings.",
    ),
    EdgarEndpoint(
        "GET",
        "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json",
        "One XBRL concept as a time series (e.g. Revenues, Assets)",
        "Preferred over companyfacts: small payload, explicit unit and frame metadata.",
    ),
    EdgarEndpoint(
        "GET",
        "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
        "Every XBRL fact for one company",
        "Large (tens of MB for big filers); only with an explicit size guard.",
    ),
    EdgarEndpoint(
        "GET",
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}&output=atom",
        "Filing index filtered by form type as an Atom feed",
        "Fallback when the submissions JSON does not cover an older filing.",
    ),
)

ACCESS_POLICY: tuple[str, ...] = (
    "Send a descriptive User-Agent with contact details on every request "
    "(EDGAR_USER_AGENT); requests without one are refused by the SEC.",
    "Stay below 10 requests per second across the whole client "
    "(EDGAR_MIN_REQUEST_INTERVAL_SECONDS defaults to 0.2s, i.e. 5/s).",
    "Cache aggressively: filings and concepts change a few times a quarter "
    "(EDGAR_CACHE_TTL_SECONDS defaults to 86400).",
    "Never treat an absent tag as a zero: EDGAR simply has no value, which must be "
    "reported as 'missing' like every other input in this product.",
    "Attribute the source in the UI and in the report, with the accession number "
    "and the filing date, exactly as the FRED adapter attributes its series.",
)


class EdgarFiling(BaseModel):
    """One filing reference (contract only in v1)."""

    cik: str
    company_name: str
    form_type: str
    accession_number: str
    filed_date: date
    primary_document_url: str
    fiscal_year: int | None = None


class EdgarFact(BaseModel):
    """One XBRL fact (contract only in v1)."""

    cik: str
    taxonomy: str = "us-gaap"
    tag: str
    unit: str
    value: float | None = None
    period_start: date | None = None
    period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form_type: str | None = None
    accession_number: str | None = None
    filed_date: date | None = None
    source_url: str = ""
    status: str = Field(default="ok", description="ok | missing | undefined")


class EdgarAdapter:
    """Interface stub. Every method documents what a real implementation must do."""

    def __init__(self, settings: EdgarSettings | None = None):
        self.settings = settings or get_edgar_settings()

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self.settings.enabled)

    @property
    def available(self) -> bool:
        """Usable right now: switched on, configured and actually implemented."""
        return self.enabled and self.settings.configured and IMPLEMENTED

    def status(self) -> dict:
        if not IMPLEMENTED:
            reason = (
                "The SEC EDGAR connector is designed but not implemented in v1. It is intentionally "
                "unavailable so that no code path can present an unfinished integration as data. "
                "See docs/market-data-sources.md for the designed interface and docs/roadmap.md (P2)."
            )
        elif not self.enabled:
            reason = "EDGAR_ENABLED is not set, so the connector is switched off."
        elif not self.settings.configured:
            reason = (
                "EDGAR_USER_AGENT is empty. The SEC fair-access policy requires a descriptive "
                "User-Agent with contact details before any request is sent."
            )
        else:
            reason = "The connector is enabled and configured."
        return {
            "connector": "sec-edgar",
            "implemented": IMPLEMENTED,
            "enabled": self.enabled,
            "configured": self.settings.configured,
            "available": self.available,
            "reason": reason,
            "access_policy": list(ACCESS_POLICY),
            "endpoints": [
                {
                    "method": endpoint.method,
                    "url_template": endpoint.url_template,
                    "purpose": endpoint.purpose,
                    "notes": endpoint.notes,
                }
                for endpoint in ENDPOINTS
            ],
            "planned_models": ["EdgarFiling", "EdgarFact"],
        }

    # ------------------------------------------------------------------
    def _refuse(self) -> None:
        if not IMPLEMENTED:
            raise EdgarNotEnabled(self.status()["reason"])
        if not self.enabled:
            raise EdgarNotEnabled("EDGAR_ENABLED is not set; no request was sent.")
        if not self.settings.configured:
            raise EdgarMisconfigured(
                "EDGAR_USER_AGENT is required by the SEC fair-access policy; no request was sent."
            )

    def resolve_cik(self, ticker: str) -> str:
        """Resolve ``ticker`` to a zero-padded 10-digit CIK.

        Implementation notes for P2: read ``company_tickers.json`` once, cache it,
        match case-insensitively, and raise a lookup error rather than guessing.
        """
        self._refuse()
        raise EdgarNotEnabled("resolve_cik is not implemented in v1")  # pragma: no cover

    def list_filings(self, cik: str, form_type: str = "10-K", limit: int = 10) -> list[EdgarFiling]:
        """Return the most recent filings of one form type.

        Implementation notes for P2: prefer ``submissions/CIK##########.json``, fall
        back to the browse-edgar Atom feed, always keep the accession number and the
        filing date, and never merge two filings of the same period.
        """
        self._refuse()
        raise EdgarNotEnabled("list_filings is not implemented in v1")  # pragma: no cover

    def get_company_concept(self, cik: str, tag: str, taxonomy: str = "us-gaap") -> list[EdgarFact]:
        """Return one XBRL concept as a time series.

        Implementation notes for P2: request ``companyconcept`` (not ``companyfacts``)
        per tag, keep the reported unit, mark gaps as ``missing`` instead of zero, and
        carry the accession number so the report can cite the filing.
        """
        self._refuse()
        raise EdgarNotEnabled("get_company_concept is not implemented in v1")  # pragma: no cover
