"""KH-01 Video-Use Planning & Creative Fidelity regression tests (T01..T11 + docs hygiene)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import probe_sources as ps  # noqa: E402
import validate_edl as ve  # noqa: E402
import verify_export as vx  # noqa: E402


def _ffmpeg_or_skip() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg not available")
    return ff


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_av_mp4(path: Path, duration_s: float = 2.0) -> None:
    ff = _ffmpeg_or_skip()
    subprocess.run(
        [
            ff, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=30:duration={duration_s}",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration_s}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
            str(path),
        ],
        check=True,
    )


def _sample_six_inventory() -> dict[str, dict[str, Any]]:
    sha = "a" * 64
    return {
        "S01": {"source_id": "S01", "media_type": "video", "relative_label": "R01/Step-1-prompt-codex.mp4", "rights_tag": "OWNED", "probe_status": "OK", "sha256": sha, "duration_s": 54.633, "width": 890, "height": 816},
        "S02": {"source_id": "S02", "media_type": "video", "relative_label": "R01/Step-2-Ask-Codex_HTML.mp4", "rights_tag": "OWNED", "probe_status": "OK", "sha256": sha, "duration_s": 41.707, "width": 906, "height": 820},
        "S03": {"source_id": "S03", "media_type": "video", "relative_label": "R01/Step-3-Show_Local-preview.mp4", "rights_tag": "OWNED", "probe_status": "OK", "sha256": sha, "duration_s": 14.767, "width": 1918, "height": 1030},
        "S04": {"source_id": "S04", "media_type": "video", "relative_label": "R01/Final-Publish.mp4", "rights_tag": "OWNED", "probe_status": "OK", "sha256": sha, "duration_s": 6.867, "width": 1442, "height": 912},
        "S05": {"source_id": "S05", "media_type": "video", "relative_label": "R01/video-doi-thu.mp4", "rights_tag": "ANALYSIS_ONLY", "probe_status": "OK", "sha256": sha, "duration_s": 16.533, "width": 1080, "height": 1920},
        "S06": {"source_id": "S06", "media_type": "video", "relative_label": "R01/video-quay canh tay.mp4", "rights_tag": "OWNED", "probe_status": "OK", "sha256": sha, "duration_s": 18.467, "width": 854, "height": 480},
        "A01": {"source_id": "A01", "media_type": "audio", "relative_label": "R02/voice.wav", "rights_tag": "GENERATED", "probe_status": "OK", "sha256": sha, "duration_s": 12.0, "width": 0, "height": 0},
        "A02": {"source_id": "A02", "media_type": "audio", "relative_label": "R02/bgm.wav", "rights_tag": "GENERATED", "probe_status": "OK", "sha256": sha, "duration_s": 12.0, "width": 0, "height": 0},
    }


def _build_valid_c2_bundle(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    mp4 = tmp_path / "exports" / "kh01_test.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    _make_av_mp4(mp4, duration_s=2.0)
    mp4_sha = _sha256_file(mp4)

    prev = tmp_path / "previews" / "p_01.png"
    prev.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [_ffmpeg_or_skip(), "-hide_banner", "-loglevel", "error", "-y", "-ss", "1.0", "-i", str(mp4), "-frames:v", "1", str(prev)],
        check=True,
    )
    prev_sha = _sha256_file(prev)

    proj_dir = tmp_path / "projects" / "p_kh01"
    proj_dir.mkdir(parents=True, exist_ok=True)
    raw_trace = tmp_path / "evidence" / "MCP_RAW_TRANSCRIPT.jsonl"
    raw_trace.parent.mkdir(parents=True, exist_ok=True)
    raw_lines = [
        {"call_id": "call-01", "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "project_create"}},
        {"call_id": "call-02", "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "timeline_read"}},
        {"call_id": "call-03", "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "preview_frame"}},
        {"call_id": "call-04", "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "project_save"}},
        {"call_id": "call-05", "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "project_close"}},
        {"call_id": "call-06", "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "project_open"}},
        {"call_id": "call-07", "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "export_start"}},
        {"call_id": "call-08", "jsonrpc": "2.0", "method": "tools/call", "params": {"name": "export_wait"}},
    ]
    raw_trace.write_text("\n".join(json.dumps(x) for x in raw_lines) + "\n", encoding="utf-8")

    mcp_ev = {
        "evidence_source": "LIVE_MCP_EXPORT_EVIDENCE",
        "run_id": "RUN_KH01",
        "project_id": "p_kh01",
        "project_path": str(proj_dir),
        "allowed_project_root": str(tmp_path / "projects"),
        "output_path": str(mp4),
        "allowed_export_root": str(tmp_path / "exports"),
        "sha256": mp4_sha,
        "concat_binary": "/Applications/Concat.app/Contents/MacOS/concat",
        "concat_binary_sha256": "b" * 64,
        "concat_version": "0.2.12",
        "mcp_mode": "headless",
        "exported_at": "2026-11-23T12:00:10Z",
        "reopen_verified": True,
        "timeline_fingerprint": "f" * 64,
        "timeline_fingerprint_before_save": "f" * 64,
        "timeline_fingerprint_after_reopen": "f" * 64,
        "raw_transcript_path": str(raw_trace),
        "raw_transcript_sha256": _sha256_file(raw_trace),
        "export_start": {"job_id": "j1", "status": "started", "started_at": "2026-11-23T12:00:00Z"},
        "export_wait": {"job_id": "j1", "status": "completed", "exit_ok": True, "completed_at": "2026-11-23T12:00:10Z"},
        "tool_trace": [
            {"tool": "project_create", "call_id": "call-01", "project_id": "p_kh01", "status": "ok"},
            {"tool": "timeline_read", "call_id": "call-02", "project_id": "p_kh01", "status": "ok"},
            {"tool": "preview_frame", "call_id": "call-03", "project_id": "p_kh01", "status": "ok"},
            {"tool": "project_save", "call_id": "call-04", "project_id": "p_kh01", "status": "ok"},
            {"tool": "project_close", "call_id": "call-05", "project_id": "p_kh01", "status": "ok"},
            {"tool": "project_open", "call_id": "call-06", "project_id": "p_kh01", "status": "ok"},
            {"tool": "export_start", "call_id": "call-07", "project_id": "p_kh01", "status": "ok"},
            {"tool": "export_wait", "call_id": "call-08", "project_id": "p_kh01", "status": "ok"},
        ],
    }
    prev_manifest = [
        {"path": str(prev), "timestamp_s": 1.0, "origin": "CONCAT_MCP_PREVIEW_FRAME", "tool_call_id": "call-03", "sha256": prev_sha}
    ]
    owner_audio_ok = {
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
    return mp4, prev, mcp_ev, prev_manifest, owner_audio_ok


def test_t01_four_video_pack_fails_six_source_preflight() -> None:
    inv = _sample_six_inventory()
    four_pack_plus_audio = {k: v for k, v in inv.items() if k in {"S01", "S02", "S03", "S04", "A01", "A02"}}
    res = ve.validate_kh01_source_pack(
        four_pack_plus_audio,
        expected_video_count=6,
        expected_filenames=["Step-1-prompt-codex.mp4", "video-doi-thu.mp4", "video-quay canh tay.mp4"],
        required_analysis_only_names=["video-doi-thu.mp4"],
    )
    assert res["status"] == "FAIL_KH01_SOURCE_PACK"
    assert res["video_source_count"] == 4
    assert any("INCOMPLETE_VIDEO_SOURCE_PACK" in e for e in res["errors"])
    assert any("MISSING_REQUIRED_SOURCE_FILES" in e for e in res["errors"])


def test_t02_six_video_inventory_roles_and_competitor_analysis_only() -> None:
    inv = _sample_six_inventory()
    ok = ve.validate_kh01_source_pack(
        inv,
        expected_video_count=6,
        required_analysis_only_names=["video-doi-thu.mp4"],
    )
    assert ok["status"] == "PASS_KH01_SOURCE_PACK"
    assert ok["video_source_count"] == 6
    assert ok["analysis_only_ids"] == ["S05"]

    bad_inv = _sample_six_inventory()
    bad_inv["S05"]["rights_tag"] = "OWNED"
    bad = ve.validate_kh01_source_pack(
        bad_inv,
        expected_video_count=6,
        required_analysis_only_names=["video-doi-thu.mp4"],
    )
    assert bad["status"] == "FAIL_KH01_SOURCE_PACK"
    assert any("REFERENCE_MUST_BE_ANALYSIS_ONLY" in e for e in bad["errors"])


def test_t03_s05_competitor_in_edl_shots_audio_or_overlay_fails() -> None:
    inv = _sample_six_inventory()
    base_edl = {
        "mode": "product_ad",
        "caption_policy": "OFF",
        "output_spec": {"width": 1080, "height": 1920, "timeline_fps": "30/1"},
        "shots": [
            {"shot_id": "SH1", "track": "V1", "source_id": "S05", "source_rights": "ANALYSIS_ONLY", "source_in_s": 0.0, "source_out_s": 2.0, "output_in_frame": 0, "output_out_frame": 60, "framing_mode": "native"}
        ],
        "overlays": [],
        "audio_tracks": [],
        "claims": [],
    }
    res_shot = ve.validate_all(base_edl, inventory=inv, validation_mode="structural", gate_phase="C2")
    assert res_shot["status"] == "FAIL_EDL_INVALID"
    assert any("FORBIDDEN_RIGHTS_IN_FINAL_EDL" in e for e in res_shot["errors"])

    overlay_edl = dict(base_edl)
    overlay_edl["shots"] = [
        {"shot_id": "SH1", "track": "V1", "source_id": "S03", "source_rights": "OWNED", "source_in_s": 0.0, "source_out_s": 2.0, "output_in_frame": 0, "output_out_frame": 60, "framing_mode": "crop_tracked"}
    ]
    overlay_edl["overlays"] = [{"overlay_id": "OV1", "overlay_type": "pip", "source_id": "S05", "source_rights": "ANALYSIS_ONLY", "output_in_frame": 0, "output_out_frame": 30}]
    res_ov = ve.validate_kh01_source_pack(inv, expected_video_count=6, edl=overlay_edl)
    assert res_ov["status"] == "FAIL_KH01_SOURCE_PACK"
    assert any("ANALYSIS_ONLY_SOURCE_IN_EDL" in e for e in res_ov["errors"])


def test_t04_authentic_hand_footage_required_or_evidenced_exception() -> None:
    inv = _sample_six_inventory()
    edl_no_hand = {
        "shots": [{"shot_id": "SH1", "source_id": "S03"}],
        "audio_tracks": [],
        "overlays": [],
    }
    res_missing = ve.validate_kh01_source_pack(inv, required_viewpoint_ids=["S06"], edl=edl_no_hand)
    assert res_missing["status"] == "FAIL_KH01_SOURCE_PACK"
    assert any("REQUIRED_VIEWPOINT_OMITTED_WITHOUT_EVIDENCE" in e for e in res_missing["errors"])

    res_exc = ve.validate_kh01_source_pack(
        inv,
        required_viewpoint_ids=["S06"],
        edl=edl_no_hand,
        viewpoint_exceptions={"S06": {"status": "SOURCE_FIDELITY_GAP", "reason": "Severe motion blur confirmed on frames", "evidence_ref": "inputs_manifest/SCENE_INDEX.json#S06"}},
    )
    assert res_exc["status"] == "PASS_KH01_SOURCE_PACK"

    edl_with_hand = {"shots": [{"shot_id": "SH1", "source_id": "S06"}], "audio_tracks": [], "overlays": []}
    res_used = ve.validate_kh01_source_pack(inv, required_viewpoint_ids=["S06"], edl=edl_with_hand)
    assert res_used["status"] == "PASS_KH01_SOURCE_PACK"


def test_t05_unverified_license_and_product_claims_fail_release(tmp_path: Path) -> None:
    inv = _sample_six_inventory()
    edl = {
        "mode": "product_ad",
        "caption_policy": "OFF",
        "output_spec": {"width": 1080, "height": 1920, "timeline_fps": "30/1"},
        "shots": [
            {"shot_id": "SH1", "track": "V1", "source_id": "S03", "source_rights": "OWNED", "source_in_s": 0.0, "source_out_s": 2.0, "output_in_frame": 0, "output_out_frame": 60, "framing_mode": "crop_tracked", "claim_evidence_ids": ["CL1"]}
        ],
        "audio_tracks": [
            {"clip_id": "VO1", "track": "A1_VO", "source_id": "A01", "source_rights": "GENERATED", "source_in_s": 0.0, "source_out_s": 2.0, "output_in_frame": 0, "output_out_frame": 60}
        ],
        "overlays": [],
        "claims": [{"claim_id": "CL1", "text": "Save 80% guaranteed today!", "status": "PLAUSIBLE_NOT_ADVERTISABLE"}],
    }
    res = ve.validate_all(edl, inventory=inv, license_ledger={}, run_dir=tmp_path, validation_mode="structural", gate_phase="C2")
    assert res["status"] == "FAIL_EDL_INVALID"
    assert any("MISSING_GENERATED_PROVENANCE" in e for e in res["errors"])
    assert any("PLAUSIBLE_CLAIM_NOT_ADVERTISABLE" in e for e in res["errors"])


def test_t06_missing_voiceover_when_vo_required_fails_creative_qa(tmp_path: Path) -> None:
    inv = _sample_six_inventory()
    edl_no_vo = {
        "mode": "product_ad",
        "voice_policy": "REQUIRED",
        "caption_policy": "OFF",
        "output_spec": {"width": 1080, "height": 1920, "timeline_fps": "30/1"},
        "shots": [
            {"shot_id": "SH1", "track": "V1", "source_id": "S03", "source_rights": "OWNED", "source_in_s": 0.0, "source_out_s": 2.0, "output_in_frame": 0, "output_out_frame": 60, "framing_mode": "crop_tracked"}
        ],
        "audio_tracks": [
            {"clip_id": "BGM1", "track": "A1_BGM", "source_id": "A02", "source_rights": "GENERATED", "source_in_s": 0.0, "source_out_s": 2.0, "output_in_frame": 0, "output_out_frame": 60}
        ],
        "overlays": [],
        "claims": [],
    }
    res_edl = ve.validate_all(edl_no_vo, inventory=inv, validation_mode="draft", gate_phase="C2")
    assert res_edl["status"] == "FAIL_EDL_INVALID"
    assert any("MISSING_REQUIRED_VO_TRACK" in e for e in res_edl["errors"])

    mp4, _, mcp_ev, prev_manifest, owner_audio = _build_valid_c2_bundle(tmp_path)
    res_exp = vx.evaluate_export(
        mp4, edl=edl_no_vo, qa_level="release", gate_phase="C2", release_policy="full-creative",
        preview_checks=prev_manifest, mcp_export_evidence=mcp_ev, perceptual_audio_evidence=owner_audio,
    )
    assert res_exp["overall_status"] == "FAIL_RELEASE_QA"
    assert "MISSING_REQUIRED_VO_TRACK" in res_exp["release_blockers"]


def test_t07_portrait_letterbox_black_bars_emits_objective_warning_and_critic_gate() -> None:
    inv = _sample_six_inventory()
    edl = {
        "mode": "product_ad",
        "caption_policy": "OFF",
        "output_spec": {"width": 1080, "height": 1920, "timeline_fps": "30/1"},
        "shots": [
            {"shot_id": "SH1", "track": "V1", "source_id": "S03", "source_rights": "OWNED", "source_in_s": 0.0, "source_out_s": 2.0, "output_in_frame": 0, "output_out_frame": 60, "framing_mode": "framed"}
        ],
        "audio_tracks": [],
        "overlays": [],
        "claims": [],
    }
    res = ve.validate_all(edl, inventory=inv, validation_mode="draft", gate_phase="C2")
    assert res["requires_human_visual_critic"] is True
    assert any("PORTRAIT_BLACK_BAR_RISK" in w for w in res["warnings"])


def test_t08_owner_audio_only_without_visual_approval_not_creative_pass(tmp_path: Path) -> None:
    mp4, _, mcp_ev, prev_manifest, owner_audio = _build_valid_c2_bundle(tmp_path)
    mp4_sha = _sha256_file(mp4)

    res_audio_only = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C2", release_policy="full-creative", require_audio=True,
        preview_checks=prev_manifest, mcp_export_evidence=mcp_ev,
        perceptual_audio_evidence=owner_audio, owner_visual_evidence=None,
    )
    assert res_audio_only["overall_status"] == "PENDING_OWNER_VISUAL_APPROVAL"
    assert res_audio_only["creative_release_gate_pass"] is False
    assert res_audio_only["production_release_pass"] is False
    assert res_audio_only["creative_production_status"] == "PENDING_OWNER_REVIEW"
    assert "OWNER_VISUAL_APPROVAL_PENDING" in res_audio_only["release_blockers"]

    owner_visual_ok = {
        "reviewer": "machine_owner",
        "reviewer_type": "OWNER_HUMAN",
        "confirmation_source": "OWNER_INTERACTION_RECORDED",
        "reviewed_at": "2026-11-23T12:06:00Z",
        "mp4_sha256": mp4_sha,
        "viewing_confirmed": True,
        "verdict": "PASS",
    }
    res_both = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C2", release_policy="full-creative", require_audio=True,
        preview_checks=prev_manifest, mcp_export_evidence=mcp_ev,
        perceptual_audio_evidence=owner_audio, owner_visual_evidence=owner_visual_ok,
    )
    assert res_both["overall_status"] == "PASS_END_TO_END_EXPORT_QA"
    assert res_both["creative_release_gate_pass"] is True
    assert res_both["production_release_pass"] is True
    assert res_both["technical_export_status"] == "PASS"
    assert res_both["creative_production_status"] == "PASS"


def test_t09_owner_creative_rejected_overrides_passing_technical_qa(tmp_path: Path) -> None:
    mp4, _, mcp_ev, prev_manifest, owner_audio = _build_valid_c2_bundle(tmp_path)
    mp4_sha = _sha256_file(mp4)

    owner_visual_reject = {
        "reviewer": "machine_owner",
        "reviewer_type": "OWNER_HUMAN",
        "confirmation_source": "OWNER_INTERACTION_RECORDED",
        "reviewed_at": "2026-11-23T12:06:00Z",
        "mp4_sha256": mp4_sha,
        "viewing_confirmed": True,
        "verdict": "CREATIVE_REJECTED",
        "rejection_reason": "Black bars and wrong opening; rebuild per R5 brief.",
    }
    res_rej = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C2", release_policy="full-creative", require_audio=True,
        preview_checks=prev_manifest, mcp_export_evidence=mcp_ev,
        perceptual_audio_evidence=owner_audio, owner_visual_evidence=owner_visual_reject,
    )
    assert res_rej["mp4_qa_pass"] is True
    assert res_rej["overall_status"] == "CREATIVE_REJECTED"
    assert res_rej["creative_production_status"] == "REJECTED"
    assert res_rej["creative_release_gate_pass"] is False
    assert res_rej["production_release_pass"] is False
    assert "CREATIVE_REJECTED_BY_OWNER" in res_rej["release_blockers"]


def test_t10_edl_release_c2_requires_real_source_integrity_hashes() -> None:
    inv = _sample_six_inventory()
    edl = {
        "mode": "product_ad",
        "caption_policy": "OFF",
        "output_spec": {"width": 1080, "height": 1920, "timeline_fps": "30/1"},
        "shots": [
            {"shot_id": "SH1", "track": "V1", "source_id": "S03", "source_rights": "OWNED", "source_in_s": 0.0, "source_out_s": 2.0, "output_in_frame": 0, "output_out_frame": 60, "framing_mode": "crop_tracked"}
        ],
        "audio_tracks": [],
        "overlays": [],
        "claims": [],
    }
    res_missing = ve.validate_all(edl, inventory=inv, validation_mode="release", gate_phase="C2", source_integrity_report=None)
    assert res_missing["status"] == "FAIL_EDL_INVALID"
    assert res_missing["release_ready"] is False

    ok_integrity = {
        "checked_at": "2026-11-23T12:00:00Z",
        "status": "PASS_SOURCES_UNCHANGED",
        "entries": [
            {
                "source_id": "S03",
                "relative_label": "R01/Step-3-Show_Local-preview.mp4",
                "expected_sha256": "a" * 64,
                "actual_sha256": "a" * 64,
                "status": "UNCHANGED",
            }
        ],
    }
    res_ok = ve.validate_all(edl, inventory=inv, validation_mode="release", gate_phase="C2", source_integrity_report=ok_integrity)
    assert res_ok["status"] == "PASS_EDL_VALID_FOR_RELEASE"
    assert res_ok["release_ready"] is True


def test_t11_probe_manifest_deterministic_across_workers_1_2_4(tmp_path: Path) -> None:
    src_dir = tmp_path / "inputs"
    src_dir.mkdir()
    for name in ("clip_b.mp4", "clip_a.mp4", "clip_c.mp4"):
        _make_av_mp4(src_dir / name, duration_s=0.6)

    snapshots = []
    for workers in (1, 2, 4):
        out_csv = tmp_path / f"inv_w{workers}.csv"
        out_json = tmp_path / f"inv_w{workers}.json"
        rc = ps.main([
            str(src_dir),
            "--out-csv", str(out_csv),
            "--out-json", str(out_json),
            "--rights-tag", "OWNED",
            "--workers", str(workers),
        ])
        assert rc == 0
        records = json.loads(out_json.read_text(encoding="utf-8"))
        canonical = [
            (r["source_id"], r["relative_label"], r["sha256"], r["bytes"], r["probe_status"])
            for r in records
        ]
        snapshots.append(canonical)
    assert snapshots[0] == snapshots[1] == snapshots[2]


def test_kh01_docs_links_and_no_niche_hardcoding_in_global_skill() -> None:
    skill_md = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    kh01_ref = (SKILL_DIR / "references" / "12_kh_01_video_use_creative_fidelity.md").read_text(encoding="utf-8")
    assert "12_kh_01_video_use_creative_fidelity.md" in skill_md
    assert "KH-01/P0" in kh01_ref and "KH-01/P3" in kh01_ref and "KH-01/QA" in kh01_ref
    assert "OWNER_VISUAL_APPROVAL" in kh01_ref and "OWNER_AUDIO_APPROVAL" in kh01_ref
    # Global skill standard must remain niche-agnostic (never hardcode Christmas/Gumroad/Video-AI(2).zip)
    for forbidden in ("Christmas", "Gumroad", "Video-AI(2).zip", "magical-christmas"):
        assert forbidden.lower() not in kh01_ref.lower(), f"Niche hardcoding found in KH-01 reference: {forbidden}"
        assert forbidden.lower() not in skill_md.lower(), f"Niche hardcoding found in SKILL.md: {forbidden}"
