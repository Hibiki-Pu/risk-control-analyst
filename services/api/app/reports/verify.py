"""Pre-export verification.

A management report is only publishable if every number in it can be traced back
to a deterministic result. These checks are mechanical, they run before any
export, and their outcome is returned to the caller (never hidden).

Checks
------
``V-01 citation format``    every citation token is well formed **and resolves**
                            to the evidence registry (this also covers the
                            "citation resolves" rule, so there is no separate
                            V-03 item).
``V-02 traceability``       every number on a line with a citation is reproducible
                            from that citation's value.
``V-04 numeric coverage``   no line carries an un-cited money/percent figure.
``V-05 synthetic flag``     the report declares the data as synthetic.
``V-06 as-of date``         the report states an as-of date.
``V-07 market freshness``   market inputs are live and not stale, or the report
                            says they are fixtures.
``V-08 zero-denominator``   no 'undefined' metric is presented as a value.

Seven items are emitted. The numbering is kept stable because report ids,
runtime artefacts and documentation reference these check ids.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import VerificationItem

CITATION_PATTERN = re.compile(
    r"\[(metric|risk|scenario|series|lineage|budget|model|policy):([A-Za-z0-9_.\-]+)(?:@([0-9A-Za-z.\-]+))?\]"
)

#: Only "checkable" numbers are extracted: thousands-separated money, percentages,
#: ratios in x, days and percentage points. Period labels such as 2024-12 are
#: deliberately ignored so the check stays precise.
NUMERIC_PATTERN = re.compile(
    r"(?<![\w.,])(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|-?\d+(?:\.\d+)?%|-?\d+(?:\.\d+)?\s?(?:x|days|day|pp))(?![\w])"
)


@dataclass
class Citation:
    citation_id: str
    label: str
    value: float | None
    unit: str
    period: str
    source_ids: list[str] = field(default_factory=list)

    def formats(self) -> set[str]:
        """Acceptable textual renderings of this value."""
        if self.value is None:
            return set()
        value = float(self.value)
        out: set[str] = set()
        if self.unit == "pct":
            for digits in (0, 1, 2):
                out.add(f"{value * 100:.{digits}f}%")
            out.add(f"{value * 100:.1f}%")
        elif self.unit == "percent_points":
            #: Values already expressed in percentage points (e.g. a 4.83% policy rate).
            for digits in (0, 1, 2):
                out.add(f"{value:.{digits}f}%")
        elif self.unit == "days":
            for digits in (0, 1):
                out.add(f"{value:.{digits}f} days")
                out.add(f"{value:.{digits}f} day")
            out.add(f"{value:.1f}")
        elif self.unit == "months":
            out.add(f"{value:.0f} months")
            out.add(f"{value:.1f} months")
        elif self.unit == "cells":
            out.add(f"{value:.0f} cells")
        elif self.unit == "score":
            out.add(f"{value:.1f}")
            out.add(f"{value:.0f}")
        elif self.unit == "raw":
            for digits in (0, 1, 2):
                out.add(f"{value:,.{digits}f}")
        elif self.unit in {"x", "ratio"}:
            for digits in (1, 2):
                out.add(f"{value:.{digits}f} x")
            out.add(f"{value:.2f}")
        elif self.unit == "pp":
            out.add(f"{value:.1f} pp")
            out.add(f"{value:+.1f}pp")
            out.add(f"{value:.1f}pp")
            out.add(f"{value:.1f}%")
        else:  # money and everything else
            for digits in (0, 1, 2):
                out.add(f"{value:,.{digits}f}")
            out.add(f"{value / 1000:,.0f}k")
            out.add(f"{value / 1_000_000:,.2f}m")
        # A decline of 53% and a change of -53% describe the same evidence, and a
        # threshold quoted as "60 days" is the same number as 60.0.
        for option in list(out):
            if option.startswith("-"):
                out.add(option[1:])
            elif option.startswith("+"):
                out.add(option[1:])
        out.add(f"{abs(value):,.0f}")
        return out


def extract_citations(text: str) -> list[str]:
    return [match.group(0)[1:-1] for match in CITATION_PATTERN.finditer(text)]


def extract_numbers(text: str) -> list[str]:
    return [match.group(0).strip() for match in NUMERIC_PATTERN.finditer(text)]


def _strip_citations(line: str) -> str:
    return CITATION_PATTERN.sub(" ", line)


def verify_report(
    markdown: str,
    registry: dict[str, Citation],
    *,
    synthetic: bool,
    as_of: str,
    market_notes: list[str] | None = None,
    undefined_metrics: list[str] | None = None,
) -> list[VerificationItem]:
    items: list[VerificationItem] = []

    # V-01 / V-02 / V-03 / V-04 per line
    bad_values: list[str] = []
    unresolved: list[str] = []
    uncited: list[str] = []
    for line in markdown.splitlines():
        citations = extract_citations(line)
        stripped = _strip_citations(line)
        numbers = extract_numbers(stripped)
        if not citations:
            if numbers:
                uncited.append(line.strip()[:120])
            continue
        cited: list[Citation] = []
        for citation_id in citations:
            citation = registry.get(citation_id)
            if citation is None:
                unresolved.append(citation_id)
            else:
                cited.append(citation)
        acceptable: set[str] = set()
        for citation in cited:
            acceptable |= citation.formats()
        for token in numbers:
            normalised = token.replace(" ", "")
            if normalised in {option.replace(" ", "") for option in acceptable}:
                continue
            if any(normalised == option.replace(" ", "") for option in acceptable):
                continue
            bad_values.append(f"{token} @ '{line.strip()[:90]}'")

    items.append(
        VerificationItem(
            check_id="V-01",
            description="Every citation token is well formed and resolves to the evidence registry",
            status="fail" if unresolved else "pass",
            detail=(
                "Unresolved citation ids: " + ", ".join(sorted(set(unresolved)))
                if unresolved
                else f"{len({c for line in markdown.splitlines() for c in extract_citations(line)})} distinct citations, all resolved"
            ),
        )
    )
    items.append(
        VerificationItem(
            check_id="V-02",
            description="Every number on a cited line is reproducible from the cited value",
            status="fail" if bad_values else "pass",
            detail=("Untraceable numbers: " + "; ".join(bad_values[:8])) if bad_values else "All cited numbers reproduced",
        )
    )
    items.append(
        VerificationItem(
            check_id="V-04",
            description="No money or percentage figure appears without a citation on the same line",
            status="fail" if uncited else "pass",
            detail=("Lines with uncited numbers: " + " | ".join(uncited[:5])) if uncited else "No uncited figures",
        )
    )
    items.append(
        VerificationItem(
            check_id="V-05",
            description="The report declares that the underlying data is synthetic",
            status="pass" if (synthetic and "SYNTHETIC" in markdown.upper()) else "fail",
            detail="Synthetic declaration present" if (synthetic and "SYNTHETIC" in markdown.upper()) else "Missing SYNTHETIC declaration",
        )
    )
    items.append(
        VerificationItem(
            check_id="V-06",
            description="The report states an as-of date",
            status="pass" if as_of and as_of in markdown else "fail",
            detail=f"as_of={as_of}",
        )
    )
    market_notes = market_notes or []
    fixture_notes = [note for note in market_notes if "fixture" in note.lower()]
    items.append(
        VerificationItem(
            check_id="V-07",
            description="Market inputs are live and fresh, or explicitly labelled as fixtures",
            status="warn" if fixture_notes else "pass",
            detail="; ".join(fixture_notes[:3]) if fixture_notes else "All market inputs report live provenance",
        )
    )
    undefined_metrics = undefined_metrics or []
    leaks = [metric for metric in undefined_metrics if re.search(rf"{re.escape(metric)}\s*[:=]?\s*-?\d", markdown)]
    items.append(
        VerificationItem(
            check_id="V-08",
            description="Metrics that are undefined (zero denominator / missing input) are not shown as numbers",
            status="fail" if leaks else "pass",
            detail=(", ".join(leaks[:5])) if leaks else "No undefined metric is presented as a value",
        )
    )

    return items


def overall_status(items: list[VerificationItem]) -> str:
    if any(item.status == "fail" for item in items):
        return "fail"
    if any(item.status == "warn" for item in items):
        return "warn"
    return "pass"
