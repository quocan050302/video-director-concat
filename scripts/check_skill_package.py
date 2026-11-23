#!/usr/bin/env python3
"""Static validator for the cross-platform video-director-concat global skill package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_PATHS = [
    "SKILL.md",
    "README_INSTALL.md",
    "MANIFEST.json",
    "references/platform_macos.md",
    "references/platform_windows.md",
    "references/00_architecture_and_modes.md",
    "references/01_source_probing_and_scene_index.md",
    "references/02_creative_direction_and_scripts.md",
    "references/03_storyboard_edl_and_mcp_mapping.md",
    "references/04_assets_tts_music_sfx_licensing.md",
    "references/05_concat_mcp_native_operations.md",
    "references/06_motion_effects_and_layout.md",
    "references/07_audio_design_and_mix.md",
    "references/08_independent_critic_and_qa.md",
    "references/09_safety_recovery_performance.md",
    "references/10_capability_and_version_matrix.md",
    "references/11_source_inspiration_license_notes.md",
    "templates/CREATIVE_BRIEF.md",
    "templates/SOURCE_INVENTORY.csv",
    "templates/HOOK_CANDIDATES.md",
    "templates/SCRIPT_AND_VO.md",
    "templates/STORYBOARD.csv",
    "templates/EDL.example.json",
    "templates/ASSET_GAPS.md",
    "templates/LICENSE_LEDGER.csv",
    "templates/COST_LEDGER.md",
    "templates/SOUND_CUE_SHEET.csv",
    "templates/CONCAT_MCP_ACTION_PLAN.example.json",
    "templates/QA_REPORT.md",
    "templates/DELIVERABLES.md",
    "templates/RUN_README.md",
    "templates/HUMAN_GATE.md",
    "scripts/platform_adapter.py",
    "scripts/probe_sources.py",
    "scripts/verify_source_hashes.py",
    "scripts/validate_edl.py",
    "scripts/verify_export.py",
    "scripts/check_skill_package.py",
    "tests/test_skill_structure.py",
    "tests/test_edl_contract.py",
    "tests/test_probe_readonly.py",
    "tests/test_qa_no_false_pass.py",
    "tests/test_platform_adapter.py",
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"BEGIN (RSA|OPENSSH|EC) PRIVATE KEY"),
]

# Detect hardcoded personal home paths while allowing documented placeholders like <local-user>
PERSONAL_PATH_PATTERNS = [
    re.compile(r"/Users/(?!<local-user>)[A-Za-z0-9._-]+/"),
    re.compile(r"C:\\Users\\(?!<local-user>)[A-Za-z0-9._-]+\\"),
]

FORBIDDEN_PIPELINE_PATTERNS = [
    re.compile(r"import\s+capcut", re.IGNORECASE),
    re.compile(r"from\s+capcut", re.IGNORECASE),
    re.compile(r"JianyingPro", re.IGNORECASE),
    re.compile(r"spctl\s+--master-disable"),
    re.compile(r"csrutil\s+disable"),
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_frontmatter(skill_md: Path) -> dict[str, Any]:
    """Validate YAML frontmatter (pure stdlib) and mandatory anti-fake-PASS clause."""
    errors: list[str] = []
    if not skill_md.exists():
        return {"status": "FAIL", "errors": ["SKILL.md missing"]}

    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, flags=re.S)
    if not m:
        return {"status": "FAIL", "errors": ["Missing valid YAML frontmatter block"]}

    fm_block = m.group(1)
    fields: dict[str, str] = {}
    current_key: str | None = None
    for line in fm_block.splitlines():
        if re.match(r"^[A-Za-z0-9_-]+\s*:", line):
            k, v = line.split(":", 1)
            current_key = k.strip()
            fields[current_key] = v.strip().strip("\"'")
        elif current_key and line.startswith((" ", "\t")):
            fields[current_key] = (fields[current_key] + " " + line.strip()).strip()

    if fields.get("name") != "video-director-concat":
        errors.append(f"Frontmatter name must be 'video-director-concat', got {fields.get('name')!r}")
    desc = fields.get("description", "")
    if len(desc) < 40:
        errors.append("Frontmatter description too short or missing")
    for kw in ("Concat", "MCP", "macOS", "Windows"):
        if kw.lower() not in desc.lower():
            errors.append(f"Frontmatter description missing keyword: {kw}")

    required_phrase = "Never claim a final exported video until Concat"
    if required_phrase.lower() not in text.lower():
        errors.append("SKILL.md missing mandatory anti-fake-PASS export rule")
    if "platform_macos.md" not in text or "platform_windows.md" not in text:
        errors.append("SKILL.md must reference both platform_macos.md and platform_windows.md")

    return {"status": "PASS" if not errors else "FAIL", "fields": fields, "errors": errors}


def validate_tree(skill_dir: Path) -> dict[str, Any]:
    missing = [rel for rel in REQUIRED_PATHS if not (skill_dir / rel).is_file()]
    return {"status": "PASS" if not missing else "FAIL", "missing": missing, "checked_count": len(REQUIRED_PATHS)}


def validate_manifest_hashes(skill_dir: Path, manifest_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not manifest_path.is_file():
        return {"status": "FAIL", "errors": ["MANIFEST.json missing"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "FAIL", "errors": [f"Invalid MANIFEST.json: {exc}"]}

    if manifest.get("name") != "video-director-concat":
        errors.append("MANIFEST.json name mismatch")
    if not manifest.get("skill_semver"):
        errors.append("MANIFEST.json missing skill_semver")

    files_list = manifest.get("files")
    if not isinstance(files_list, list) or not files_list:
        return {"status": "FAIL", "errors": ["MANIFEST.json missing non-empty files list"]}

    listed_paths: set[str] = set()
    for entry in files_list:
        rel = entry.get("path", "")
        if rel == "MANIFEST.json":
            errors.append("SELF_REFERENTIAL_MANIFEST_FORBIDDEN: MANIFEST.json must not hash itself")
            continue
        listed_paths.add(rel)
        target = skill_dir / rel
        if not target.is_file():
            errors.append(f"MANIFEST_FILE_MISSING: {rel}")
            continue
        actual_size = target.stat().st_size
        actual_sha = _sha256_file(target)
        if actual_size != entry.get("bytes"):
            errors.append(f"SIZE_MISMATCH: {rel} actual={actual_size} manifest={entry.get('bytes')}")
        if actual_sha != entry.get("sha256"):
            errors.append(f"SHA256_MISMATCH: {rel}")

    # Verify no untracked stray files inside skill tree
    for p in sorted(skill_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(skill_dir).as_posix()
        if rel == "MANIFEST.json":
            continue
        if ".git" in p.parts or "__pycache__" in p.parts or ".pytest_cache" in p.parts or p.name == ".DS_Store":
            continue
        if rel not in listed_paths:
            errors.append(f"UNTRACKED_FILE_IN_SKILL: {rel}")

    return {"status": "PASS" if not errors else "FAIL", "file_count": len(listed_paths), "errors": errors}


def scan_for_secrets_and_hardcoded_user_paths(skill_dir: Path) -> dict[str, Any]:
    findings: list[str] = []
    for p in sorted(skill_dir.rglob("*")):
        if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts or ".pytest_cache" in p.parts:
            continue
        if p.suffix.lower() not in {".md", ".py", ".json", ".csv", ".txt", ".yml", ".yaml"}:
            continue
        rel = p.relative_to(skill_dir).as_posix()
        # Skip self-regex definitions inside check_skill_package.py
        if rel == "scripts/check_skill_package.py":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                findings.append(f"SECRET_PATTERN_DETECTED: {rel} ({pat.pattern})")
        for pat in PERSONAL_PATH_PATTERNS:
            if pat.search(text):
                findings.append(f"HARDCODED_USER_PATH: {rel} ({pat.pattern})")
    return {"status": "PASS" if not findings else "FAIL", "findings": findings}


def validate_no_capcut_engine_in_new_pipeline(skill_dir: Path) -> dict[str, Any]:
    violations: list[str] = []
    for p in sorted((skill_dir / "scripts").glob("*.py")):
        if p.name in {"check_skill_package.py", "platform_adapter.py"}:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for pat in FORBIDDEN_PIPELINE_PATTERNS:
            if pat.search(text):
                violations.append(f"FORBIDDEN_CALL_IN_SCRIPT: {p.name} ({pat.pattern})")
    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace") if (skill_dir / "SKILL.md").exists() else ""
    if "Concat" not in skill_text or "CapCut" not in skill_text:
        violations.append("SKILL.md must explicitly lock Concat as sole engine and exclude CapCut")
    return {"status": "PASS" if not violations else "FAIL", "violations": violations}


def run_all_checks(skill_dir: Path) -> dict[str, Any]:
    results = {
        "frontmatter": validate_frontmatter(skill_dir / "SKILL.md"),
        "tree": validate_tree(skill_dir),
        "manifest_hashes": validate_manifest_hashes(skill_dir, skill_dir / "MANIFEST.json"),
        "secrets_and_paths": scan_for_secrets_and_hardcoded_user_paths(skill_dir),
        "no_capcut_engine": validate_no_capcut_engine_in_new_pipeline(skill_dir),
    }
    all_pass = all(r["status"] == "PASS" for r in results.values())
    return {
        "skill_dir": str(skill_dir),
        "status": "PASS_SKILL_STATIC_READY" if all_pass else "FAIL_SKILL_STATIC",
        "checks": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate video-director-concat skill package.")
    parser.add_argument("--skill-dir", type=Path, required=True, help="Path to video-director-concat directory.")
    parser.add_argument("--out", type=Path, help="Optional JSON report path.")
    args = parser.parse_args(argv)

    report = run_all_checks(args.skill_dir.resolve())
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS_SKILL_STATIC_READY" else 1


if __name__ == "__main__":
    sys.exit(main())
