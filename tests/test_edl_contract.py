"""EDL contract, rights, frame-grid, aspect, and mode constraint tests (T04, T07, T08, T10, T11, T13)."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import validate_edl as ve  # noqa: E402


def _example_edl() -> dict:
    return json.loads((SKILL_DIR / "templates" / "EDL.example.json").read_text(encoding="utf-8"))


def _make_run_dir(tmp_path: Path) -> Path:
    (tmp_path / "SOURCE_TRUTH.md").write_text("# Source Truth\n- U001: verified product studio shot.\n", encoding="utf-8")
    ev = tmp_path / "evidence"
    ev.mkdir(exist_ok=True)
    (ev / "lic1_terms.txt").write_text("Commercial video license verified.\n", encoding="utf-8")
    return tmp_path


def _sample_inventory() -> dict:
    return {
        "U001": {
            "source_id": "U001",
            "root_id": "R01",
            "relative_label": "owned_studio_01.mp4",
            "media_type": "video",
            "rights_tag": "OWNED",
            "sha256": "a" * 64,
            "duration_s": 5.0,
            "width": 1080,
            "height": 1920,
            "probe_status": "OK",
        },
        "U002": {
            "source_id": "U002",
            "root_id": "R01",
            "relative_label": "owned_usage_02.mp4",
            "media_type": "video",
            "rights_tag": "OWNED",
            "sha256": "b" * 64,
            "duration_s": 6.0,
            "width": 1920,
            "height": 1080,
            "probe_status": "OK",
        },
        "U003": {
            "source_id": "U003",
            "root_id": "R01",
            "relative_label": "owned_bgm_03.wav",
            "media_type": "audio",
            "rights_tag": "OWNED",
            "sha256": "c" * 64,
            "duration_s": 10.0,
            "width": 0,
            "height": 0,
            "probe_status": "OK",
        },
        "REF1": {
            "source_id": "REF1",
            "root_id": "R01",
            "relative_label": "competitor_ref.mp4",
            "media_type": "video",
            "rights_tag": "ANALYSIS_ONLY",
            "sha256": "d" * 64,
            "duration_s": 10.0,
            "width": 1080,
            "height": 1920,
            "probe_status": "OK",
        },
        "LIC1": {
            "source_id": "LIC1",
            "root_id": "R01",
            "relative_label": "licensed_broll.mp4",
            "media_type": "video",
            "rights_tag": "LICENSED",
            "sha256": "e" * 64,
            "duration_s": 8.0,
            "width": 1920,
            "height": 1080,
            "probe_status": "OK",
        },
    }


def _integrity_for(inv: dict) -> dict:
    return {
        "checked_at": "2026-11-23T13:00:00Z",
        "status": "PASS_SOURCES_UNCHANGED",
        "entries": [
            {
                "source_id": sid,
                "root_id": m["root_id"],
                "relative_label": m["relative_label"],
                "expected_sha256": m["sha256"],
                "actual_sha256": m["sha256"],
                "status": "UNCHANGED",
            }
            for sid, m in inv.items()
        ],
    }


def test_t04_example_edl_valid(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    inv = _sample_inventory()
    res_struct = ve.validate_all(_example_edl(), inv, run_dir=run_dir, validation_mode="structural")
    assert res_struct["status"] == "PASS_EDL_STRUCTURAL_ONLY", res_struct["errors"]
    assert res_struct["release_ready"] is False

    res_rel = ve.validate_all(
        _example_edl(), inv, run_dir=run_dir,
        source_integrity_report=_integrity_for(inv), validation_mode="release",
    )
    assert res_rel["status"] == "PASS_EDL_VALID_FOR_RELEASE", res_rel["errors"]
    assert res_rel["release_ready"] is True


def test_t07_out_of_duration_and_speed_mismatch_rejected(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    edl = _example_edl()
    edl["shots"][0]["source_out_s"] = 9.5
    res = ve.validate_all(edl, _sample_inventory(), run_dir=run_dir, validation_mode="release")
    assert res["status"] == "FAIL_EDL_INVALID"
    assert any("SOURCE_OUT_EXCEEDS_DURATION" in e for e in res["errors"])


def test_t08_analysis_only_blocked_from_final_edl(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    edl = _example_edl()
    edl["shots"][0]["source_id"] = "REF1"
    edl["shots"][0]["source_rights"] = "ANALYSIS_ONLY"
    res = ve.validate_all(edl, _sample_inventory(), run_dir=run_dir, validation_mode="release")
    assert res["status"] == "FAIL_EDL_INVALID"
    assert any("FORBIDDEN_RIGHTS_IN_FINAL_EDL" in e for e in res["errors"])


def test_t08_licensed_without_ledger_rejected_and_approved_passes(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    inv = _sample_inventory()
    edl = _example_edl()
    edl["shots"][1]["source_id"] = "LIC1"
    edl["shots"][1]["source_rights"] = "LICENSED"
    res_missing = ve.validate_all(edl, inv, license_ledger={}, run_dir=run_dir, validation_mode="release")
    assert res_missing["status"] == "FAIL_EDL_INVALID"
    assert any("MISSING_LICENSE_LEDGER_ENTRY" in e for e in res_missing["errors"])

    ledger = {
        "LIC1": {
            "asset_id": "LIC1",
            "decision": "APPROVED",
            "commercial_use_allowed": "YES",
            "license_url": "https://example.org/commercial-license",
            "license_evidence_path": "evidence/lic1_terms.txt",
        }
    }
    res_ok = ve.validate_all(
        edl, inv, license_ledger=ledger, run_dir=run_dir,
        source_integrity_report=_integrity_for(inv), validation_mode="release",
    )
    assert res_ok["status"] == "PASS_EDL_VALID_FOR_RELEASE", res_ok["errors"]


def test_t11_horizontal_and_portrait_supported_and_landscape_in_portrait_checked(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    inv = _sample_inventory()
    edl_16x9 = _example_edl()
    edl_16x9["output_spec"] = {"width": 1920, "height": 1080, "timeline_fps": "24/1", "aspect_ratio": "16:9"}
    for s in edl_16x9["shots"]:
        s["timeline_fps"] = "24/1"
    edl_16x9["shots"][0]["output_in_frame"] = 0
    edl_16x9["shots"][0]["output_out_frame"] = 72
    edl_16x9["shots"][1]["output_in_frame"] = 72
    edl_16x9["shots"][1]["output_out_frame"] = 144
    res_16x9 = ve.validate_all(
        edl_16x9, inv, run_dir=run_dir,
        source_integrity_report=_integrity_for(inv), validation_mode="release",
    )
    assert res_16x9["status"] == "PASS_EDL_VALID_FOR_RELEASE", res_16x9["errors"]

    edl_bad_crop = _example_edl()
    edl_bad_crop["shots"][1]["framing_mode"] = "native"
    res_bad = ve.validate_all(edl_bad_crop, inv, run_dir=run_dir, validation_mode="release")
    assert res_bad["status"] == "FAIL_EDL_INVALID"
    assert any("LANDSCAPE_IN_PORTRAIT_NEEDS_EXPLICIT_FRAMING" in e for e in res_bad["errors"])


def test_t13_caption_policy_and_claim_removal(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    inv = _sample_inventory()
    edl = _example_edl()
    edl["caption_policy"] = "OFF"
    edl["overlays"].append({"overlay_id": "C001", "overlay_type": "karaoke", "text": "Hello"})
    res_off = ve.validate_all(edl, inv, run_dir=run_dir, validation_mode="release")
    assert res_off["status"] == "FAIL_EDL_INVALID"
    assert any("UNAUTHORIZED_CAPTION_OVERLAY" in e for e in res_off["errors"])

    edl_on = copy.deepcopy(edl)
    edl_on["caption_policy"] = "ON"
    res_on = ve.validate_all(
        edl_on, inv, run_dir=run_dir,
        source_integrity_report=_integrity_for(inv), validation_mode="release",
    )
    assert res_on["status"] == "PASS_EDL_VALID_FOR_RELEASE", res_on["errors"]

    edl_claim = _example_edl()
    edl_claim["claims"].append({"claim_id": "E999", "text": "Unverified 10x ROI", "status": "UNKNOWN_REMOVE"})
    res_claim = ve.validate_all(edl_claim, inv, run_dir=run_dir, validation_mode="release")
    assert res_claim["status"] == "FAIL_EDL_INVALID"
    assert any("UNVERIFIED_CLAIM_PRESENT" in e for e in res_claim["errors"])


def test_timeline_gap_and_unintended_overlap_rejected(tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    edl_gap = _example_edl()
    edl_gap["shots"][1]["output_in_frame"] = 100
    edl_gap["shots"][1]["output_out_frame"] = 190
    res_gap = ve.validate_all(edl_gap, _sample_inventory(), run_dir=run_dir, validation_mode="release")
    assert any("TIMELINE_GAP" in e for e in res_gap["errors"])

    edl_ov = _example_edl()
    edl_ov["shots"][1]["output_in_frame"] = 80
    edl_ov["shots"][1]["output_out_frame"] = 170
    res_ov = ve.validate_all(edl_ov, _sample_inventory(), run_dir=run_dir, validation_mode="release")
    assert any("UNINTENDED_OVERLAP" in e for e in res_ov["errors"])
