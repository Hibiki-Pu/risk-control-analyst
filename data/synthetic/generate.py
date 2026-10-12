#!/usr/bin/env python
"""Regenerate the synthetic demo dataset.

    python data/synthetic/generate.py --write          # write CSV/JSON files
    python data/synthetic/generate.py --check          # validate the files on disk
    python data/synthetic/generate.py --seed 12345 --write

The generator is deterministic: the same seed always produces byte-identical
files. Everything it writes is fictional demo material.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from app.data.synthetic import (  # noqa: E402
    DECLARED_GAPS,
    N_MONTHS,
    SEED,
    generate_dataset,
    load_dataset,
    validate_dataset,
    write_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="RiskControl Analyst synthetic data generator")
    parser.add_argument("--seed", type=int, default=SEED, help="random seed (default: %(default)s)")
    parser.add_argument("--months", type=int, default=N_MONTHS, help="number of months (default: %(default)s)")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "synthetic", help="output directory")
    parser.add_argument("--write", action="store_true", help="write the files to disk")
    parser.add_argument("--check", action="store_true", help="validate the files currently on disk")
    args = parser.parse_args()

    if args.check:
        dataset = load_dataset(args.out)
        issues = validate_dataset(dataset)
        print(f"Validated {args.out}")
        print(json.dumps(dataset.manifest.get("row_counts", {}), indent=2))
        if issues:
            print("ISSUES:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        print("No issues found.")
        print("Declared gaps:", json.dumps(DECLARED_GAPS, ensure_ascii=False))
        return 0

    dataset = generate_dataset(seed=args.seed, n_months=args.months)
    issues = validate_dataset(dataset)
    if issues:
        print("Generation produced an invalid dataset:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    months = dataset.months
    print(f"Generated {len(dataset.financials)} fact rows across {len(months)} months ({months[0]}..{months[-1]})")
    print(f"Regions: {sorted(dataset.financials['region'].unique().tolist())}")
    print(f"Declared gaps: {len(DECLARED_GAPS)}")

    if args.write:
        manifest = write_dataset(dataset, args.out)
        print(f"Wrote files to {args.out}")
        print(json.dumps(manifest["sha256"], indent=2))
    else:
        print("Dry run: pass --write to persist the files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
