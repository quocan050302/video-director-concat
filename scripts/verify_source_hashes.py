#!/usr/bin/env python3
"""Verify original source files remain byte-for-byte unchanged via SHA-256 (QA.R3 hardened).

Supports single-root (--base-dir) and multi-root (--root R01=/path/a --root R02=/path/b)
inventories, rejecting POSIX & Windows path traversal, symlinks (leaf or parent),
non-regular files (directories/FIFOs), and duplicate source_id entries.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
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


def _is_safe_rel(rel: str) -> bool:
    if not rel or "\x00" in rel or any(ord(c) < 32 for c in rel):
        return False
    if rel.startswith(("/", "\\")):
        return False
    if re.match(r"^[A-Za-z]:", rel):
        return False
    parts = re.split(r"[/\\]+", rel)
    if ".." in parts:
        return False
    if Path(rel).is_absolute():
        return False
    return True


def load_manifest(path: str | Path) -> list[dict[str, Any]]:
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


def _has_symlink_component(root: Path, rel_subpath: Path) -> bool:
    cur = root
    for part in rel_subpath.parts:
        cur = cur / part
        if cur.is_symlink():
            return True
    return False


def _resolve_target(
    rel: str,
    root_id: str,
    base_dir: Path | None,
    root_map: dict[str, Path],
) -> tuple[Path | None, Path | None, str | None]:
    if not _is_safe_rel(rel):
        return None, None, "PATH_ESCAPE_REJECTED"

    if root_map:
        prefix, sep, inner = rel.partition("/")
        if sep and prefix in root_map:
            root = root_map[prefix].resolve()
            sub_rel = Path(inner)
        elif root_id and root_id in root_map:
            root = root_map[root_id].resolve()
            sub_rel = Path(rel)
        else:
            return None, None, f"UNKNOWN_ROOT_ID:{root_id or prefix}"
    elif base_dir is not None:
        root = base_dir.resolve()
        sub_rel = Path(rel)
    else:
        return None, None, "MISSING_BASE_DIR_OR_ROOT_MAP"

    if _has_symlink_component(root, sub_rel):
        return None, root, "SYMLINK_REJECTED"

    raw_cand = root / sub_rel
    try:
        resolved = raw_cand.resolve()
        resolved.relative_to(root)
    except ValueError:
        return None, root, "PATH_ESCAPE_REJECTED"

    if resolved.exists() and not resolved.is_file():
        return None, root, "NOT_A_REGULAR_FILE"
    return resolved, root, None


def verify_unchanged(
    records: list[dict[str, Any]],
    base_dir: str | Path | None = None,
    root_map: dict[str, str | Path] | None = None,
) -> dict[str, Any]:
    """Re-hash every source against recorded baseline; never mutates originals."""
    base_p = Path(base_dir).resolve() if base_dir is not None else None
    rmap = {k: Path(v).resolve() for k, v in (root_map or {}).items()}
    checked: list[dict[str, Any]] = []
    drifted: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for rec in records:
        rel = str(rec.get("relative_label") or rec.get("path") or "").strip()
        root_id = str(rec.get("root_id") or "R01").strip()
        expected_sha = str(rec.get("sha256") or "").strip().lower()
        source_id = str(rec.get("source_id") or rel).strip()
        if not rel or not expected_sha:
            drifted.append({"source_id": source_id, "reason": "INVALID_BASELINE_ENTRY"})
            continue

        if source_id in seen_ids:
            drifted.append({"source_id": source_id, "relative_label": rel, "reason": "DUPLICATE_MANIFEST_SOURCE_ID"})
            continue
        seen_ids.add(source_id)

        candidate, _, err = _resolve_target(rel, root_id, base_p, rmap)
        if err:
            drifted.append({"source_id": source_id, "relative_label": rel, "reason": err})
            continue
        assert candidate is not None
        if not candidate.exists():
            missing.append({"source_id": source_id, "relative_label": rel, "expected_sha256": expected_sha})
            continue

        actual_sha = _stream_sha256(candidate)
        entry = {
            "source_id": source_id,
            "root_id": root_id,
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
        "unchanged_count": len(checked) - sum(1 for e in checked if e["status"] != "UNCHANGED"),
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
    parser.add_argument("--base-dir", type=Path, help="Single root directory containing original sources.")
    parser.add_argument("--root", action="append", default=[], help="Multi-root mapping R01=/path/to/dir (repeatable).")
    parser.add_argument("--out", type=Path, help="Optional JSON drift report output.")
    args = parser.parse_args(argv)

    rmap: dict[str, str] = {}
    for item in args.root:
        if "=" not in item:
            parser.error(f"Invalid --root value {item!r}, expected R01=/path")
        k, v = item.split("=", 1)
        rmap[k.strip()] = v.strip()

    if args.base_dir is None and not rmap:
        parser.error("Provide --base-dir or at least one --root R01=/path")

    records = load_manifest(args.manifest)
    report = verify_unchanged(records, base_dir=args.base_dir, root_map=rmap or None)
    if args.out:
        write_drift_report(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS_SOURCES_UNCHANGED" else 1


if __name__ == "__main__":
    sys.exit(main())
