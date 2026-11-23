"""Static package integrity tests (T01, T02, T03, T14)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import check_skill_package as csp  # noqa: E402


def test_t01_frontmatter_valid() -> None:
    res = csp.validate_frontmatter(SKILL_DIR / "SKILL.md")
    assert res["status"] == "PASS", res["errors"]
    assert res["fields"]["name"] == "video-director-concat"


def test_t02_required_tree_complete() -> None:
    res = csp.validate_tree(SKILL_DIR)
    assert res["status"] == "PASS", f"Missing files: {res['missing']}"


def test_t03_manifest_hashes_and_no_self_hash() -> None:
    manifest_path = SKILL_DIR / "MANIFEST.json"
    res = csp.validate_manifest_hashes(SKILL_DIR, manifest_path)
    assert res["status"] == "PASS", res["errors"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listed = [f["path"] for f in manifest["files"]]
    assert "MANIFEST.json" not in listed


def test_t03_no_secrets_or_hardcoded_user_paths() -> None:
    res = csp.scan_for_secrets_and_hardcoded_user_paths(SKILL_DIR)
    assert res["status"] == "PASS", res["findings"]


def test_no_capcut_engine_in_new_pipeline() -> None:
    res = csp.validate_no_capcut_engine_in_new_pipeline(SKILL_DIR)
    assert res["status"] == "PASS", res["violations"]


def test_t14_templates_include_run_readme_and_human_gate() -> None:
    run_readme = (SKILL_DIR / "templates" / "RUN_README.md").read_text(encoding="utf-8")
    human_gate = (SKILL_DIR / "templates" / "HUMAN_GATE.md").read_text(encoding="utf-8")
    assert "Run ID" in run_readme
    assert "PENDING_OWNER_SECURITY_APPROVAL" in human_gate
