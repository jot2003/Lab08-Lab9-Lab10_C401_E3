#!/usr/bin/env python3
"""
Final readiness gate for Day 10 submissions.

Checks high-impact rubric items before final merge/push:
- required docs/artifacts exist
- grading JSONL includes gq_d10_01..03
- manifest has core counters
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path}: line {i} invalid JSON: {e}") from e
    return rows


def _check_exists(paths: Iterable[Path]) -> list[str]:
    msgs: list[str] = []
    for p in paths:
        if p.is_file():
            msgs.append(f"OK file: {p}")
        else:
            msgs.append(f"FAIL missing file: {p}")
    return msgs


def main() -> int:
    root = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Day10 final readiness checker")
    p.add_argument("--manifest", default=str(root / "artifacts" / "manifests" / "manifest_dung-after-final.json"))
    p.add_argument("--grading", default=str(root / "artifacts" / "eval" / "grading_run.jsonl"))
    args = p.parse_args()

    required_files = [
        root / "docs" / "pipeline_architecture.md",
        root / "docs" / "data_contract.md",
        root / "docs" / "runbook.md",
        root / "docs" / "quality_report.md",
        root / "reports" / "group_report.md",
        Path(args.manifest),
        Path(args.grading),
        root / "artifacts" / "eval" / "dung_before_bad_eval.csv",
        root / "artifacts" / "eval" / "dung_after_final_eval.csv",
    ]

    messages = _check_exists(required_files)
    exit_code = 0
    for m in messages:
        print(m)
        if m.startswith("FAIL"):
            exit_code = 1

    manifest = Path(args.manifest)
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for key in ("run_id", "raw_records", "cleaned_records", "quarantine_records"):
            if key in data:
                print(f"OK manifest key: {key}={data[key]}")
            else:
                print(f"FAIL manifest missing key: {key}")
                exit_code = 1

    grading = Path(args.grading)
    if grading.is_file():
        rows = _load_jsonl(grading)
        ids = {str(r.get("id")) for r in rows}
        for gid in ("gq_d10_01", "gq_d10_02", "gq_d10_03"):
            if gid in ids:
                print(f"OK grading row: {gid}")
            else:
                print(f"FAIL grading row missing: {gid}")
                exit_code = 1

    if exit_code == 0:
        print("READY: submission gate passed.")
    else:
        print("NOT_READY: fix FAIL items above.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
