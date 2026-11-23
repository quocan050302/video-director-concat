"""QA.R1 Bug Reproduction & Comprehensive Hardening Regression Suite (R02–R23)."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import check_skill_package as csp  # noqa: E402
import platform_adapter as pa  # noqa: E402
import probe_sources as ps  # noqa: E402
import validate_edl as ve  # noqa: E402
import verify_export as vx  # noqa: E402
import verify_source_hashes as vsh  # noqa: E402

VALID_SHA = "a" * 64


def _ffmpeg_or_skip() -> str:
    b = shutil.which("ffmpeg")
    if not b:
        pytest.skip("ffmpeg not installed")
    return b


def _valid_inventory() -> dict[str, dict]:
    return {
        "U001": {
            "source_id": "U001",
            "relative_label": "owned_a.mp4",
            "media_type": "video",
            "rights_tag": "OWNED",
            "sha256": VALID_SHA,
            "duration_s": 5.0,
            "width": 1080,
            "height": 1920,
            "probe_status": "OK",
        },
        "U002": {
            "source_id": "U002",
            "relative_label": "owned_b.mp4",
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
            "relative_label": "owned_audio.wav",
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
            "relative_label": "competitor.mp4",
            "media_type": "video",
            "rights_tag": "ANALYSIS_ONLY",
            "sha256": "d" * 64,
            "duration_s": 8.0,
            "width": 1080,
            "height": 1920,
            "probe_status": "OK",
        },
        "LIC1": {
            "source_id": "LIC1",
            "relative_label": "stock.mp4",
            "media_type": "video",
            "rights_tag": "LICENSED",
            "sha256": "e" * 64,
            "duration_s": 8.0,
            "width": 1920,
            "height": 1080,
            "probe_status": "OK",
        },
        "GEN1": {
            "source_id": "GEN1",
            "relative_label": "local_vo.wav",
            "media_type": "audio",
            "rights_tag": "GENERATED",
            "sha256": "f" * 64,
            "duration_s": 8.0,
            "width": 0,
            "height": 0,
            "probe_status": "OK",
        },
        "IMG1": {
            "source_id": "IMG1",
            "relative_label": "still.png",
            "media_type": "image",
            "rights_tag": "OWNED",
            "sha256": "1" * 64,
            "duration_s": 0.0,
            "width": 1080,
            "height": 1920,
            "probe_status": "OK",
        },
    }


def _valid_edl() -> dict:
    return json.loads((SKILL_DIR / "templates" / "EDL.example.json").read_text(encoding="utf-8"))


def _make_av_mp4(dest: Path, duration_s: float = 2.0, static_color: str | None = None, size: str = "320x240") -> None:
    ffmpeg_bin = _ffmpeg_or_skip()
    v_in = (
        f"color=c={static_color}:s={size}:d={duration_s}:r=30"
        if static_color
        else f"testsrc2=duration={duration_s}:size={size}:rate=30"
    )
    subprocess.run(
        [
            ffmpeg_bin, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", v_in,
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_s}",
            "-af", "volume=-16dB",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", str(dest),
        ],
        check=True,
    )


# --- P0-01 (R08, R09): EDL Rights & Inventory Fail-Closed ---

def test_p0_01_r08_missing_inventory_fails_release_and_draft_cannot_claim_release() -> None:
    edl = _valid_edl()
    res_release = ve.validate_all(edl, inventory={}, validation_mode="release")
    assert res_release["status"] == "FAIL_EDL_INVALID"
    assert res_release["release_ready_edl"] is False
    assert any("MISSING_SOURCE_INVENTORY" in e for e in res_release["errors"])

    res_draft = ve.validate_all(edl, inventory={}, validation_mode="draft")
    assert res_draft["status"] == "PASS_EDL_DRAFT_ONLY"
    assert res_draft["release_ready_edl"] is False


def test_p0_01_r08_unknown_id_bad_probe_bad_sha_and_overlay_analysis_only_blocked() -> None:
    inv = _valid_inventory()

    edl_u999 = _valid_edl()
    edl_u999["shots"][0]["source_id"] = "U999"
    res_u999 = ve.validate_all(edl_u999, inventory=inv, validation_mode="release")
    assert res_u999["status"] == "FAIL_EDL_INVALID"
    assert any("SOURCE_ID_NOT_IN_INVENTORY" in e for e in res_u999["errors"])

    inv_unk = copy.deepcopy(inv)
    inv_unk["U001"]["rights_tag"] = "UNKNOWN_RIGHTS"
    res_unk = ve.validate_all(_valid_edl(), inventory=inv_unk, validation_mode="release")
    assert res_unk["status"] == "FAIL_EDL_INVALID"
    assert any("FORBIDDEN_RIGHTS_IN_FINAL_EDL" in e for e in res_unk["errors"])

    inv_bad = copy.deepcopy(inv)
    inv_bad["U001"]["probe_status"] = "PROBE_FAILED"
    inv_bad["U002"]["sha256"] = "not-a-sha"
    res_bad = ve.validate_all(_valid_edl(), inventory=inv_bad, validation_mode="release")
    assert any("SOURCE_PROBE_NOT_OK" in e for e in res_bad["errors"])
    assert any("INVALID_SOURCE_SHA256" in e for e in res_bad["errors"])

    edl_ov = _valid_edl()
    edl_ov["overlays"].append({"overlay_id": "OV_REF", "overlay_type": "broll_pip", "source_id": "REF1"})
    res_ov = ve.validate_all(edl_ov, inventory=inv, validation_mode="release")
    assert res_ov["status"] == "FAIL_EDL_INVALID"
    assert any("FORBIDDEN_RIGHTS_IN_FINAL_EDL" in e for e in res_ov["errors"])


def test_p0_01_r09_licensed_evidence_and_generated_provenance_enforced(tmp_path: Path) -> None:
    (tmp_path / "SOURCE_TRUTH.md").write_text("# Truth\n- U001: verified product shot.\n", encoding="utf-8")
    ev_dir = tmp_path / "evidence"
    ev_dir.mkdir()
    (ev_dir / "lic1_terms.txt").write_text("Commercial license archived.\n", encoding="utf-8")
    (ev_dir / "kokoro_license.txt").write_text("Apache-2.0 code + Apache-2.0 weights + af_heart voice.\n", encoding="utf-8")
    inv = _valid_inventory()

    edl_lic = _valid_edl()
    edl_lic["shots"][1]["source_id"] = "LIC1"
    edl_lic["shots"][1]["source_rights"] = "LICENSED"
    weak_ledger = {
        "LIC1": {
            "asset_id": "LIC1",
            "decision": "APPROVED",
            "commercial_use_allowed": "YES",
            "license_url": "",
            "license_evidence_path": "",
        }
    }
    res_weak = ve.validate_all(edl_lic, inventory=inv, license_ledger=weak_ledger, run_dir=tmp_path, validation_mode="release")
    assert res_weak["status"] == "FAIL_EDL_INVALID"
    assert any("MISSING_LICENSE_EVIDENCE" in e for e in res_weak["errors"])

    strong_ledger = {
        "LIC1": {
            "asset_id": "LIC1",
            "decision": "APPROVED",
            "commercial_use_allowed": "YES",
            "license_url": "https://example.org/license",
            "license_evidence_path": "evidence/lic1_terms.txt",
            "attribution_required": "NO",
            "redistribution_restrictions": "NO_RESALE",
        }
    }
    res_ok = ve.validate_all(edl_lic, inventory=inv, license_ledger=strong_ledger, run_dir=tmp_path, validation_mode="structural")
    assert res_ok["status"] == "PASS_EDL_STRUCTURAL_ONLY", res_ok["errors"]

    edl_gen = _valid_edl()
    edl_gen["audio_tracks"][0]["source_id"] = "GEN1"
    edl_gen["audio_tracks"][0]["source_rights"] = "GENERATED"
    res_gen_fail = ve.validate_all(edl_gen, inventory=inv, license_ledger={}, run_dir=tmp_path, validation_mode="release")
    assert res_gen_fail["status"] == "FAIL_EDL_INVALID"
    assert any("MISSING_GENERATED_PROVENANCE" in e for e in res_gen_fail["errors"])

    gen_ledger = {
        "GEN1": {
            "asset_id": "GEN1",
            "decision": "APPROVED",
            "commercial_use_allowed": "YES",
            "license_name": "Apache-2.0 code + Apache-2.0 Kokoro-82M weights + af_heart voice",
            "license_url": "https://huggingface.co/hexgrad/Kokoro-82M",
            "license_evidence_path": "evidence/kokoro_license.txt",
            "attribution_required": "NO",
            "redistribution_restrictions": "NONE",
        }
    }
    res_gen_ok = ve.validate_all(edl_gen, inventory=inv, license_ledger=gen_ledger, run_dir=tmp_path, validation_mode="structural")
    assert res_gen_ok["status"] == "PASS_EDL_STRUCTURAL_ONLY", res_gen_ok["errors"]


# --- P0-02 (R10): Claim Evidence Truth Gate ---

def test_p0_02_r10_claim_evidence_truth_gate(tmp_path: Path) -> None:
    inv = _valid_inventory()

    edl_empty = _valid_edl()
    edl_empty["claims"][0]["evidence_ref"] = ""
    res_empty = ve.validate_all(edl_empty, inventory=inv, validation_mode="release")
    assert any("MISSING_CLAIM_EVIDENCE_REF" in e for e in res_empty["errors"])

    edl_nofile = _valid_edl()
    edl_nofile["claims"][0]["evidence_ref"] = "DOES_NOT_EXIST.md#U001"
    res_nofile = ve.validate_all(edl_nofile, inventory=inv, run_dir=tmp_path, validation_mode="release")
    assert any("CLAIM_EVIDENCE_FILE_NOT_FOUND" in e for e in res_nofile["errors"])

    # Real evidence file resolves cleanly (structural pass; release requires on-disk source integrity)
    (tmp_path / "SOURCE_TRUTH.md").write_text("# Truth\nU001 verified.\n", encoding="utf-8")
    res_file_ok = ve.validate_all(_valid_edl(), inventory=inv, run_dir=tmp_path, validation_mode="structural")
    assert res_file_ok["status"] == "PASS_EDL_STRUCTURAL_ONLY", res_file_ok["errors"]

    edl_trav = _valid_edl()
    edl_trav["claims"][0]["evidence_ref"] = "../../etc/passwd"
    res_trav = ve.validate_all(edl_trav, inventory=inv, run_dir=tmp_path, validation_mode="release")
    assert any("UNSAFE_CLAIM_EVIDENCE_REF" in e for e in res_trav["errors"])

    edl_url = _valid_edl()
    edl_url["claims"][0]["evidence_ref"] = "https://example.com/unverified-promo"
    res_url = ve.validate_all(edl_url, inventory=inv, validation_mode="release")
    assert any("UNVERIFIED_EXTERNAL_CLAIM_URI" in e for e in res_url["errors"])

    edl_ref = _valid_edl()
    edl_ref["claims"][0]["evidence_ref"] = "SOURCE_TRUTH.md#REF1"
    res_ref = ve.validate_all(edl_ref, inventory=inv, validation_mode="release")
    assert any("CLAIM_CITES_ANALYSIS_ONLY_SOURCE" in e for e in res_ref["errors"])

    edl_dup = _valid_edl()
    edl_dup["claims"].append({"claim_id": "E001", "text": "dup", "status": "MAGIC_STATUS", "evidence_ref": "SOURCE_TRUTH.md#U001"})
    res_dup = ve.validate_all(edl_dup, inventory=inv, validation_mode="release")
    assert any("DUPLICATE_CLAIM_ID" in e for e in res_dup["errors"])
    assert any("UNKNOWN_CLAIM_STATUS" in e for e in res_dup["errors"])

    edl_num = _valid_edl()
    edl_num["claims"].append({"claim_id": "E002", "text": "Save 50% guaranteed today!", "status": "PLAUSIBLE_NOT_ADVERTISABLE", "evidence_ref": "SOURCE_TRUTH.md#U001"})
    edl_num["shots"][0]["claim_evidence_ids"].append("E002")
    res_num = ve.validate_all(edl_num, inventory=inv, validation_mode="release")
    assert any("PLAUSIBLE_CLAIM_NOT_ADVERTISABLE" in e for e in res_num["errors"])


# --- P1-03 (R07): Rational FPS, Speed, Invalid Numerics & Layered V2 ---

def test_p1_03_r07_rational_fps_speed_invalid_numerics_and_layered_v2(tmp_path: Path) -> None:
    (tmp_path / "SOURCE_TRUTH.md").write_text("# Truth\n- U001 verified.\n", encoding="utf-8")
    inv = _valid_inventory()

    # Invalid numerics fail cleanly with zero uncaught TypeError
    edl = _valid_edl()
    edl["shots"][0]["speed"] = float("nan")
    edl["shots"][0]["safe_region_normalized"] = ["0.1", True, 0.9, 0.8]
    edl["shots"][1]["output_in_frame"] = True
    res = ve.validate_all(edl, inventory=inv, run_dir=tmp_path, validation_mode="release")
    assert res["status"] == "FAIL_EDL_INVALID"
    assert any("INVALID_SPEED" in e for e in res["errors"])
    assert any("INVALID_SAFE_REGION" in e for e in res["errors"])
    assert any("NON_INTEGER_FRAME_BOUNDS" in e for e in res["errors"])

    # Invalid FPS values: zero, negative, NaN, malformed
    for bad_fps in ("0/1", "-30/1", "NaN", "not_fps", True):
        bad_edl = _valid_edl()
        bad_edl["output_spec"]["timeline_fps"] = bad_fps
        errs = ve.validate_frame_grid(bad_edl)
        assert errs, f"Expected error for fps={bad_fps!r}"

    # Valid NTSC 30000/1001 with 1.5x speed (3.0s source / 1.5 = 2.0s -> 60 frames at 29.97fps)
    edl_ntsc = _valid_edl()
    edl_ntsc["output_spec"]["timeline_fps"] = "30000/1001"
    edl_ntsc["shots"][0].update({"timeline_fps": "30000/1001", "source_in_s": 0.5, "source_out_s": 3.5, "speed": 1.5, "output_in_frame": 0, "output_out_frame": 60})
    edl_ntsc["shots"][1].update({"timeline_fps": "30000/1001", "source_in_s": 1.0, "source_out_s": 2.5, "speed": 0.75, "output_in_frame": 60, "output_out_frame": 120})
    edl_ntsc["overlays"][0].update({"output_in_frame": 10, "output_out_frame": 50})
    edl_ntsc["audio_tracks"][0].update({"source_out_s": 4.0, "output_out_frame": 120})
    res_ntsc = ve.validate_all(edl_ntsc, inventory=inv, run_dir=tmp_path, validation_mode="structural")
    assert res_ntsc["status"] == "PASS_EDL_STRUCTURAL_ONLY", res_ntsc["errors"]

    # Valid V2 overlay shot + owned still image shot passes cleanly
    edl_v2 = _valid_edl()
    edl_v2["shots"].append({
        "shot_id": "S_V2_01",
        "track": "V2",
        "mode": "product_ad",
        "source_id": "IMG1",
        "source_rights": "OWNED",
        "source_in_s": 0.0,
        "source_out_s": 2.0,
        "speed": 1.0,
        "output_in_frame": 30,
        "output_out_frame": 90,
        "timeline_fps": "30/1",
        "framing_mode": "native",
        "safe_region_normalized": [0.1, 0.1, 0.9, 0.9],
    })
    res_v2 = ve.validate_all(edl_v2, inventory=inv, run_dir=tmp_path, validation_mode="structural")
    assert res_v2["status"] == "PASS_EDL_STRUCTURAL_ONLY", res_v2["errors"]


# --- P0-03 (R12, R13, R14, R15, R16, R22): Export Provenance, Preview & EOF Freeze ---

def test_p0_03_r14_r15_r16_r22_release_blocks_without_mcp_provenance_preview_and_perceptual(tmp_path: Path) -> None:
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    proj_dir = tmp_path / "projects" / "PRJ_SMOKE_01"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.concat").write_text("{}", encoding="utf-8")
    mp4 = exports_dir / "UNIT_SYNTHETIC_FFMPEG_FIXTURE_NOT_CONCAT_EXPORT.mp4"
    _make_av_mp4(mp4, duration_s=2.0)

    r_tech = vx.evaluate_export(mp4, qa_level="technical", require_audio=True)
    assert r_tech["overall_status"] == "PASS_TECHNICAL_ONLY"
    assert r_tech["release_gate_pass"] is False

    r_rel_none = vx.evaluate_export(mp4, qa_level="release", require_audio=True)
    assert r_rel_none["release_gate_pass"] is False
    assert any("NO_MCP_PROVENANCE" in e for e in r_rel_none["release_blockers"])
    assert any("PREVIEW_MISSING" in e for e in r_rel_none["release_blockers"])

    assert vx.main(["--mp4", str(mp4), "--qa-level", "release"]) != 0
    assert vx.main(["--mp4", str(mp4), "--qa-level", "technical"]) == 0

    prev_png = tmp_path / "prev_1.0s.png"
    subprocess.run(
        [_ffmpeg_or_skip(), "-hide_banner", "-loglevel", "error", "-ss", "1.0", "-i", str(mp4), "-frames:v", "1", "-y", str(prev_png)],
        check=True,
    )
    prev_sha = hashlib.sha256(prev_png.read_bytes()).hexdigest()
    mp4_sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
    trace_rows = [
        {"tool": "project_create", "call_id": "c1", "project_id": "PRJ_SMOKE_01", "status": "ok", "ts": "2026-11-23T11:59:50Z"},
        {"tool": "timeline_read", "call_id": "c2", "project_id": "PRJ_SMOKE_01", "status": "ok", "ts": "2026-11-23T11:59:51Z"},
        {"tool": "preview_frame", "call_id": "c3", "project_id": "PRJ_SMOKE_01", "status": "ok", "ts": "2026-11-23T11:59:52Z"},
        {"tool": "project_save", "call_id": "c4", "project_id": "PRJ_SMOKE_01", "status": "ok", "ts": "2026-11-23T11:59:53Z"},
        {"tool": "project_close", "call_id": "c5", "project_id": "PRJ_SMOKE_01", "status": "ok", "ts": "2026-11-23T11:59:54Z"},
        {"tool": "project_open", "call_id": "c6", "project_id": "PRJ_SMOKE_01", "status": "ok", "ts": "2026-11-23T11:59:55Z"},
        {"tool": "export_start", "call_id": "c7", "project_id": "PRJ_SMOKE_01", "status": "ok", "ts": "2026-11-23T11:59:58Z"},
        {"tool": "export_wait", "call_id": "c8", "project_id": "PRJ_SMOKE_01", "status": "ok", "ts": "2026-11-23T11:59:59Z"},
    ]
    raw_jsonl = tmp_path / "MCP_RAW_TRACE.jsonl"
    raw_jsonl.write_text("\n".join(json.dumps(r) for r in trace_rows) + "\n", encoding="utf-8")
    raw_sha = hashlib.sha256(raw_jsonl.read_bytes()).hexdigest()
    mcp_ev = {
        "evidence_source": "LIVE_MCP_EXPORT_EVIDENCE",
        "project_id": "PRJ_SMOKE_01",
        "project_path": str(proj_dir),
        "allowed_project_root": str(tmp_path / "projects"),
        "run_id": "RUN_01",
        "concat_binary": "/Applications/Concat.app/Contents/MacOS/concat",
        "concat_binary_sha256": "1" * 64,
        "concat_version": "0.2.12",
        "mcp_mode": "headless",
        "export_start": {"job_id": "JOB_01", "status": "started", "started_at": "2026-11-23T11:59:58Z"},
        "export_wait": {"job_id": "JOB_01", "status": "completed", "exit_ok": True, "completed_at": "2026-11-23T11:59:59Z"},
        "reopen_verified": True,
        "timeline_fingerprint": "fp_abc123",
        "timeline_fingerprint_before_save": "fp_abc123",
        "timeline_fingerprint_after_reopen": "fp_abc123",
        "tool_trace": trace_rows,
        "raw_transcript_path": str(raw_jsonl),
        "raw_transcript_sha256": raw_sha,
        "output_path": str(mp4),
        "allowed_export_root": str(exports_dir),
        "sha256": mp4_sha,
        "exported_at": "2026-11-23T12:00:00Z",
    }
    prev_manifest = [
        {"path": str(prev_png), "timestamp_s": 1.0, "origin": "CONCAT_MCP_PREVIEW_FRAME", "tool_call_id": "c3", "sha256": prev_sha}
    ]

    # Tampered/failed MCP provenance cases MUST fail
    bad_wait = copy.deepcopy(mcp_ev)
    bad_wait["export_wait"] = {"job_id": "JOB_01", "status": "failed", "exit_ok": False, "completed_at": "2026-11-23T11:59:59Z"}
    assert vx.validate_mcp_export_provenance(bad_wait, r_tech["probe"])["status"] == "FAIL_MCP_PROVENANCE"

    bad_sha = copy.deepcopy(mcp_ev)
    bad_sha["sha256"] = "0" * 64
    assert vx.validate_mcp_export_provenance(bad_sha, r_tech["probe"])["status"] == "FAIL_MCP_PROVENANCE"

    bad_root = copy.deepcopy(mcp_ev)
    bad_root["allowed_export_root"] = str(tmp_path / "other_dir")
    assert vx.validate_mcp_export_provenance(bad_root, r_tech["probe"])["status"] == "FAIL_MCP_PROVENANCE"

    # Real provenance schema + preview WITHOUT OWNER_HUMAN listening -> PENDING_PERCEPTUAL_AUDIO
    r_rel_pending = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C1", release_policy="full-creative", require_audio=True,
        preview_checks=prev_manifest, mcp_export_evidence=mcp_ev,
    )
    assert r_rel_pending["mp4_qa_pass"] is True
    assert r_rel_pending["audio_perceptual_status"] == "PERCEPTUAL_AUDIO_PENDING"
    assert r_rel_pending["creative_release_gate_pass"] is False
    assert r_rel_pending["release_gate_pass"] is False
    assert r_rel_pending["overall_status"] == "PENDING_PERCEPTUAL_AUDIO"

    # Explicit C1 technical-smoke policy sets technical_e2e_gate_pass=True but NEVER creative_release_gate_pass=True
    r_tech_rel = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C1", release_policy="technical-smoke", require_audio=True,
        preview_checks=prev_manifest, mcp_export_evidence=mcp_ev,
    )
    assert r_tech_rel["overall_status"] == "C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING"
    assert r_tech_rel["technical_e2e_gate_pass"] is True
    assert r_tech_rel["creative_release_gate_pass"] is False
    assert r_tech_rel["release_gate_pass"] is False

    # Validator unit test with OWNER_HUMAN interaction checklist + raw transcript (unit parser test only, NOT live proof)
    perceptual_ev = {
        "reviewer": "machine_owner",
        "reviewer_type": "OWNER_HUMAN",
        "confirmation_source": "OWNER_INTERACTION_RECORDED",
        "reviewed_at": "2026-11-23T12:05:00Z",
        "mp4_sha256": mp4_sha,
        "playback_confirmed": True,
        "verdict": "PASS",
        "auditory_checklist": {
            "intelligibility": True,
            "pops_clicks": True,
            "ducking": True,
            "sync": True,
            "no_unexpected_silence": True,
        },
    }
    r_rel_pass = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C1", release_policy="full-creative", require_audio=True,
        preview_checks=prev_manifest, mcp_export_evidence=mcp_ev,
        perceptual_audio_evidence=perceptual_ev,
    )
    assert r_rel_pass["creative_release_gate_pass"] is True
    assert r_rel_pass["overall_status"] == "PASS_END_TO_END_EXPORT_QA"
    assert r_rel_pass["preview_comparisons"][0]["ssim"] >= 0.75


def test_p0_03_r13_r14_eof_freeze_ffmpeg_error_and_preview_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_mp4 = tmp_path / "eof_freeze.mp4"
    _make_av_mp4(freeze_mp4, duration_s=2.5, static_color="blue")
    bf = vx.detect_unintended_blacks_and_freezes(freeze_mp4, edl=None)
    assert bf["status"] == "FAIL_UNINTENDED_BLACK_OR_FREEZE"
    assert len(bf["unintended_freezes"]) >= 1

    # Wrong-size preview image & visually mismatched preview image MUST fail
    wrong_size_png = tmp_path / "wrong_size.png"
    subprocess.run(
        [_ffmpeg_or_skip(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=160x120:d=0.1", "-frames:v", "1", "-y", str(wrong_size_png)],
        check=True,
    )
    cmp_size = vx.compare_preview_export_frame(wrong_size_png, freeze_mp4, 1.0, expected_dims=(320, 240))
    assert cmp_size["status"] == "FAIL_PREVIEW_DIMENSION_MISMATCH"

    red_same_size = tmp_path / "red_320x240.png"
    subprocess.run(
        [_ffmpeg_or_skip(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=0.1", "-frames:v", "1", "-y", str(red_same_size)],
        check=True,
    )
    cmp_diff = vx.compare_preview_export_frame(red_same_size, freeze_mp4, 1.0, expected_dims=(320, 240))
    assert cmp_diff["status"] == "FAIL_PREVIEW_MISMATCH"

    # Missing ffmpeg blocks release decode instead of silent PASS
    real_which = shutil.which
    monkeypatch.setattr(vx.shutil, "which", lambda name: None if name == "ffmpeg" else real_which(name))
    r_noff = vx.probe_export(freeze_mp4, require_full_decode=True)
    assert r_noff["status"] == "BLOCKED_ENV_FFMPEG_MISSING"

    # Simulated ffmpeg non-zero exit in black/freeze detection -> FAIL_BLACK_FREEZE_FFMPEG_ERROR
    monkeypatch.setattr(vx.shutil, "which", real_which)
    fake_proc = subprocess.CompletedProcess(args=["ffmpeg"], returncode=1, stdout="", stderr="simulated filter error")
    monkeypatch.setattr(vx.subprocess, "run", lambda *_a, **_kw: fake_proc)
    r_err = vx.detect_unintended_blacks_and_freezes(freeze_mp4, edl=None, duration_s=2.5)
    assert r_err["status"] == "FAIL_BLACK_FREEZE_FFMPEG_ERROR"


# --- P1-01 (R05, R06, R18): Bounded Traversal, Multi-Root Disambiguation & Determinism ---

def test_p1_01_r05_r06_r18_bounded_scan_multi_root_and_determinism(tmp_path: Path) -> None:
    big_dir = tmp_path / "big"
    big_dir.mkdir()
    for i in range(120):
        (big_dir / f"clip_{i:03d}.mp4").write_bytes(b"x")
    disc, rej = ps.discover_inputs(
        [str(big_dir)],
        limits={"max_files": 50, "max_entries_scanned": 40, "max_dirs_scanned": 10},
    )
    assert len(disc) <= 40
    assert any("SCAN_BUDGET_REACHED" in r["reason"] for r in rej)

    # Zero-byte and corrupt file fail probing cleanly without crashing
    bad_dir = tmp_path / "bad_media"
    bad_dir.mkdir()
    (bad_dir / "zero.mp4").write_bytes(b"")
    (bad_dir / "corrupt.mp4").write_bytes(b"not a real video")
    assert ps.probe_media(bad_dir / "corrupt.mp4")["probe_status"] == "PROBE_FAILED"

    # Multi-root duplicate filenames + determinism across repeated runs (R18)
    r1 = tmp_path / "root_a"
    r2 = tmp_path / "root_b"
    r1.mkdir()
    r2.mkdir()
    _make_av_mp4(r1 / "same.mp4", duration_s=1.2)
    _make_av_mp4(r2 / "same.mp4", duration_s=1.4)

    out_csv_1, out_json_1 = tmp_path / "inv1.csv", tmp_path / "inv1.json"
    out_csv_2, out_json_2 = tmp_path / "inv2.csv", tmp_path / "inv2.json"
    stills = tmp_path / "stills"

    rc1 = ps.main([str(r1), str(r2), "--out-csv", str(out_csv_1), "--out-json", str(out_json_1), "--contact-dir", str(stills), "--rights-tag", "OWNED", "--workers", "2"])
    rc2 = ps.main([str(r1), str(r2), "--out-csv", str(out_csv_2), "--out-json", str(out_json_2), "--contact-dir", str(stills), "--rights-tag", "OWNED", "--workers", "1"])
    assert rc1 == 0 and rc2 == 0
    assert out_csv_1.read_text(encoding="utf-8") == out_csv_2.read_text(encoding="utf-8")

    rows = vsh.load_manifest(out_csv_1)
    assert len(rows) == 2
    assert rows[0]["relative_label"] != rows[1]["relative_label"]
    assert rows[0]["vfr_detection_method"] == "header_rate_heuristic_non_definitive"
    assert len(list(stills.glob("*.jpg"))) >= 4

    verify_res = vsh.verify_unchanged(rows, base_dir=None, root_map={"R01": r1, "R02": r2})
    assert verify_res["status"] == "PASS_SOURCES_UNCHANGED"


# --- P1-02 (R03, R21): Platform Adapter Source-Built Binary, Version & Disk Guard ---

def test_p1_02_r03_r21_source_build_version_fallback_ffprobe_decouple_and_disk_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_bin = tmp_path / "Concat" / "src" / "target" / "release" / "concat"
    fake_bin.parent.mkdir(parents=True)
    fake_bin.write_text("#!/bin/sh\necho 'concat 0.2.12-source'\n", encoding="utf-8")
    fake_bin.chmod(0o755)

    prof = pa.detect_platform_profile(system="Darwin", machine="arm64", os_version="14.4.1", home_dir="/Users/<local-user>")
    found = pa.discover_concat_binary(prof, source_checkouts=[tmp_path / "Concat"])
    assert found["binary_status"] == "BINARY_FOUND"
    assert found["binary_source"] == "SOURCE_BUILD_RELEASE"
    assert "0.2.12-source" in found["app_version"]
    assert found["app_sha256"] is not None

    # Binary whose --version fails -> VERSION_PENDING_MCP (never NOT_INSTALLED!)
    no_ver_bin = tmp_path / "concat_nover"
    no_ver_bin.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    no_ver_bin.chmod(0o755)
    found_nv = pa.discover_concat_binary(prof, explicit_binary=no_ver_bin)
    assert found_nv["binary_status"] == "BINARY_FOUND"
    assert found_nv["app_version"] == "VERSION_PENDING_MCP"

    # Low disk (<5 GB) MUST block c0_ready_for_mcp even when binary exists
    monkeypatch.setattr(pa, "_disk_usage_gb", lambda _p: (2.5, 460.0))
    monkeypatch.setattr(pa, "discover_concat_binary", lambda *_a, **_kw: found)
    env_low = pa.probe_host_environment()
    assert env_low["disk_safety_status"] == "DISK_BLOCK"
    assert env_low["c0_ready_for_mcp"] is False
    assert env_low["c0_status"] == "BLOCKED_LOW_DISK"

    # Adequate disk + missing ffprobe still allows c0_ready_for_mcp while flagging qa_media_tools_status
    monkeypatch.setattr(pa, "_disk_usage_gb", lambda _p: (40.0, 460.0))
    monkeypatch.setattr(pa, "_probe_binary_version", lambda name, *_a: {"found": False, "path": None, "version": "MISSING"} if name == "ffprobe" else {"found": True, "path": "/bin/x", "version": "ok"})
    env_noff = pa.probe_host_environment()
    assert env_noff["c0_ready_for_mcp"] is True
    assert env_noff["qa_media_tools_status"] == "QA_TOOLS_FFPROBE_MISSING"


# --- P1-03 (R02): Manifest Hardening ---

def test_p1_03_r02_manifest_rejects_duplicate_traversal_symlink_and_count_mismatch(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "escape_link.txt").symlink_to(outside)
    sha_a = hashlib.sha256(b"hello").hexdigest()

    bad_manifest = {
        "name": "video-director-concat",
        "skill_semver": "1.0.0",
        "file_count": 99,
        "files": [
            {"path": "a.txt", "bytes": 5, "sha256": sha_a},
            {"path": "a.txt", "bytes": 5, "sha256": sha_a},
            {"path": "../outside.txt", "bytes": 1, "sha256": "0" * 64},
        ],
    }
    mp = tmp_path / "MANIFEST.json"
    mp.write_text(json.dumps(bad_manifest), encoding="utf-8")
    res = csp.validate_manifest_hashes(tmp_path, mp)
    assert res["status"] == "FAIL"
    joined = "\n".join(res["errors"])
    assert "DUPLICATE_MANIFEST_ENTRY" in joined
    assert "UNSAFE_MANIFEST_PATH" in joined
    assert "FILE_COUNT_MISMATCH" in joined
    assert "SYMLINK_ESCAPE_IN_SKILL" in joined
