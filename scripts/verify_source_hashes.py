#!/usr/bin/env python3
"""Verify original source files remain byte-for-byte unchanged via SHA-256."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _stream_sha256(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_manifest(path: str | Path) -> list[dict[str, Any]]:
    """Load source baseline records from SOURCE_INVENTORY.csv or JSON."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "files" in data:
            return list(data["files"])
        if isinstance(data, list):
            return data
        raise ValueError("Unsupported JSON manifest format")

    with open(p, "r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def verify_unchanged(records: list[dict[str, Any]], base_dir: str | Path) -> dict[str, Any]:
    """Re-hash every source against recorded baseline; never mutates originals."""
    root = Path(base_dir).resolve()
    checked: list[dict[str, Any]] = []
    drifted: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for rec in records:
        rel = rec.get("relative_label") or rec.get("path")
        expected_sha = (rec.get("sha256") or "").strip().lower()
        source_id = rec.get("source_id") or rel
        if not rel or not expected_sha:
            drifted.append({"source_id": source_id, "reason": "INVALID_BASELINE_ENTRY"})
            continue

        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            drifted.append({"source_id": source_id, "relative_label": rel, "reason": "PATH_ESCAPE_REJECTED"})
            continue

        if not candidate.exists():
            missing.append({"source_id": source_id, "relative_label": rel, "expected_sha256": expected_sha})
            continue

        actual_sha = _stream_sha256(candidate)
        entry = {
            "source_id": source_id,
            "relative_label": rel,
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "status": "UNCHANGED" if actual_sha == expected_sha else "DRIFT_DETECTED",
        }
        checked.append(entry)
        if actual_sha != expected_sha:
            drifted.append(entry)

    passed = len(records) > 0 and not drifted and not missing
    return {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "PASS_SOURCES_UNCHANGED" if passed else "FAIL_SOURCE_DRIFT_OR_MISSING",
        "total_records": len(records),
        "unchanged_count": len(checked) - len(drifted),
        "drifted": drifted,
        "missing": missing,
        "entries": checked,
    }


def write_drift_report(report: dict[str, Any], out_path: str | Path) -> None:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify original sources match baseline SHA-256.")
    parser.add_argument("--manifest", type=Path, required=True, help="SOURCE_INVENTORY.csv or JSON manifest.")
    parser.add_argument("--base-dir", type=Path, required=True, help="Root directory containing original sources.")
    parser.add_argument("--out", type=Path, help="Optional JSON drift report output.")
    args = parser.parse_args(argv)

    records = load_manifest(args.manifest)
    report = verify_unchanged(records, args.base_dir)
    if args.out:
        write_drift_report(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS_SOURCES_UNCHANGED" else 1


if __name__ == "__main__":
    sys.exit(main())
