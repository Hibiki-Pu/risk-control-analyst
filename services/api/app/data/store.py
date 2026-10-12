"""Dataset store: the seed dataset, plus optionally one uploaded dataset.

Only one dataset is active at a time. The seed dataset is the default and is the
only one that ships with a budget layer; an uploaded file is finance-actuals only
and the budget endpoints then answer "not available" instead of inventing a plan.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.core.config import Settings, get_settings
from app.data import SyntheticDataset
from app.data.ingest import IngestReport, ingest
from app.finance.engine import FinancialEngine
from app.data.synthetic import load_dataset


@dataclass
class ActiveDataset:
    dataset_id: str
    label: str
    kind: str  # "synthetic_seed" | "uploaded_file"
    dataset: SyntheticDataset
    synthetic: bool
    source_path: str | None = None


class DatasetStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.uploads_dir = self.settings.runtime_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._active: ActiveDataset | None = None
        self._engine: FinancialEngine | None = None
        self._uploads: dict[str, dict] = {}

    # ------------------------------------------------------------------
    def seed_dir(self) -> Path:
        return Path(self.settings.data_dir)

    def ensure_seed(self) -> ActiveDataset:
        if self._active is not None and self._active.kind == "synthetic_seed":
            return self._active
        source = self.seed_dir()
        if not (source / "monthly_financials.csv").exists():
            raise FileNotFoundError(
                f"Seed data not found in {source}. Run: python data/synthetic/generate.py --write"
            )
        dataset = load_dataset(source)
        self._active = ActiveDataset(
            dataset_id=str(dataset.manifest.get("dataset_id", "synthetic-aurelia-v1")),
            label=str(dataset.profile.get("display_name", "Synthetic demo company")),
            kind="synthetic_seed",
            dataset=dataset,
            synthetic=bool(self.settings.synthetic_data),
            source_path=str(source),
        )
        self._engine = None
        return self._active

    def active(self) -> ActiveDataset:
        return self._active or self.ensure_seed()

    def engine(self) -> FinancialEngine:
        if self._engine is None:
            current = self.active()
            self._engine = FinancialEngine(
                current.dataset, dataset_id=current.dataset_id, synthetic=current.synthetic
            )
        return self._engine

    # ------------------------------------------------------------------
    def ingest_upload(self, content: bytes, filename: str, activate: bool = True) -> dict:
        report, frame = ingest(content, filename)
        upload_id = f"UP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
        record = {
            "upload_id": upload_id,
            "filename": filename,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "report": report.to_dict(),
            "activated": False,
        }
        if report.passed:
            target = self.uploads_dir / f"{upload_id}.csv"
            frame.to_csv(target, index=False, encoding="utf-8")
            record["stored_path"] = str(target)
            if activate:
                self._activate_upload(upload_id, frame, filename, target)
                record["activated"] = True
        self._uploads[upload_id] = record
        return record

    def _activate_upload(self, upload_id: str, frame: pd.DataFrame, filename: str, path: Path) -> None:
        empty_budget = pd.DataFrame(
            columns=[
                "month",
                "budget_revenue_usd",
                "budget_cogs_usd",
                "budget_opex_usd",
                "budget_depreciation_amortization_usd",
                "budget_interest_expense_usd",
                "budget_capex_usd",
                "budget_note",
            ]
        )
        macro = self.ensure_seed().dataset.macro
        dataset = SyntheticDataset(
            financials=frame,
            budget=empty_budget,
            macro=macro,
            profile={
                "company_id": upload_id,
                "display_name": f"Uploaded dataset ({filename})",
                "display_name_zh": f"上传数据集（{filename}）",
                "industry": "n/a — user supplied",
                "regions": [
                    {"code": code, "name": code, "currency": currency}
                    for code, currency in frame.groupby("region")["currency"].first().items()
                ],
                "reporting_currency": "USD",
                "local_currencies": sorted(frame["currency"].astype(str).unique().tolist()),
                "fiscal_year_end": "12-31",
                "period_range": {
                    "start": str(frame["month"].min()),
                    "end": str(frame["month"].max()),
                    "months": int(frame["month"].nunique()),
                },
                "consolidation_note": "Uploaded fact table. Amounts are assumed to be in USD after translation.",
                "synthetic": False,
                "disclaimer": "User-supplied file. Not verified against any external source by this application.",
                "generator": {"module": "upload", "version": "1.0.0", "seed": None},
            },
            manifest={
                "dataset_id": upload_id,
                "source": filename,
                "row_counts": {"monthly_financials": int(len(frame))},
                "synthetic": False,
            },
        )
        self._active = ActiveDataset(
            dataset_id=upload_id,
            label=f"Uploaded: {filename}",
            kind="uploaded_file",
            dataset=dataset,
            synthetic=False,
            source_path=str(path),
        )
        self._engine = None

    def activate_seed(self) -> ActiveDataset:
        self._active = None
        self._engine = None
        return self.ensure_seed()

    def uploads(self) -> list[dict]:
        return sorted(self._uploads.values(), key=lambda item: item["received_at"], reverse=True)

    def upload(self, upload_id: str) -> dict | None:
        return self._uploads.get(upload_id)

    def manifest(self) -> dict:
        current = self.active()
        return {
            "dataset_id": current.dataset_id,
            "label": current.label,
            "kind": current.kind,
            "synthetic": current.synthetic,
            "source_path": current.source_path,
            "rows": int(len(current.dataset.financials)),
            "months": current.dataset.months,
            "regions": sorted(current.dataset.financials["region"].unique().tolist()),
            "has_budget_layer": bool(len(current.dataset.budget)),
            "disclaimer": current.dataset.profile.get("disclaimer"),
        }

    def seed_manifest(self) -> dict:
        try:
            return json.loads((self.seed_dir() / "dataset_manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
