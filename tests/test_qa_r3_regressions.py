"""QA.R3 Adversarial Bug Reproduction & Regression Suite (R3-01 through R3-25).

Every synthetic media fixture created here is strictly:
  UNIT_SYNTHETIC_FFMPEG_FIXTURE_NOT_CONCAT_EXPORT
and every simulated MCP dict is strictly:
  UNIT_SIMULATED_PROVENANCE
Never treated as live Concat export proof.
"""

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

FIXTURE_TAG = "UNIT_SYNTHETIC_FFMPEG_FIXTURE_NOT_CONCAT_EXPORT"


def _ffmpeg_or_skip() -> str:
    b = shutil.which("ffmpeg")
    if not b:
        pytest.skip("ffmpeg not installed")
    return b


def _make_unit_mp4(dest: Path, duration_s: float = 1.6, with_audio: bool = True) -> None:
    ffmpeg_bin = _ffmpeg_or_skip()
    cmd = [
        ffmpeg_bin, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=duration={duration_s}:size=320x240:rate=30",
    ]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_s}", "-af", "volume=-16dB", "-c:a", "aac", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += ["-pix_fmt", "yuv420p", "-y", str(dest)]
    subprocess.run(cmd, check=True)


def _extract_png(mp4: Path, png: Path, t_s: float = 0.8) -> str:
    subprocess.run(
        [_ffmpeg_or_skip(), "-hide_banner", "-loglevel", "error", "-ss", str(t_s), "-i", str(mp4), "-frames:v", "1", "-y", str(png)],
        check=True,
    )
    return hashlib.sha256(png.read_bytes()).hexdigest()


def _base_inventory() -> dict[str, dict]:
    return {
        "U001": {"source_id": "U001", "root_id": "R01", "relative_label": "a.mp4", "media_type": "video", "rights_tag": "OWNED", "sha256": "a" * 64, "duration_s": 5.0, "width": 1080, "height": 1920, "probe_status": "OK"},
        "U002": {"source_id": "U002", "root_id": "R01", "relative_label": "b.mp4", "media_type": "video", "rights_tag": "OWNED", "sha256": "b" * 64, "duration_s": 6.0, "width": 1920, "height": 1080, "probe_status": "OK"},
        "U003": {"source_id": "U003", "root_id": "R01", "relative_label": "c.wav", "media_type": "audio", "rights_tag": "OWNED", "sha256": "c" * 64, "duration_s": 10.0, "width": 0, "height": 0, "probe_status": "OK"},
    }


def _valid_integrity_report(inv: dict[str, dict]) -> dict:
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


# --- PHASE C (R3-01, R3-02, R3-03, R3-24): EDL Structural vs Final Release & Source Integrity ---

def test_r3_01_02_03_24_edl_release_requires_verified_per_file_source_integrity(tmp_path: Path) -> None:
    (tmp_path / "SOURCE_TRUTH.md").write_text("# Truth\n- U001 verified.\n", encoding="utf-8")
    edl = json.loads((SKILL_DIR / "templates" / "EDL.example.json").read_text(encoding="utf-8"))
    inv = _base_inventory()

    # R3-01: Release EDL without on-disk source_integrity_report CANNOT return PASS_EDL_VALID_FOR_RELEASE or release_ready=True!
    res_no_int = ve.validate_all(edl, inventory=inv, run_dir=tmp_path, validation_mode="release")
    assert res_no_int["release_ready"] is False
    assert res_no_int["status"] != "PASS_EDL_VALID_FOR_RELEASE"

    # R3-02: C2 / C4 release gate MUST fail-closed even if caller passed require_source_integrity=False!
    for phase in ("C2", "C4"):
        res_c = ve.validate_all(
            edl, inventory=inv, run_dir=tmp_path,
            validation_mode="release", gate_phase=phase, require_source_integrity=False,
        )
        assert res_c["status"] == "FAIL_EDL_INVALID"
        assert res_c["release_ready"] is False
        assert any("MISSING_SOURCE_INTEGRITY_CHECK" in e for e in res_c["errors"])

    # R3-03: Forged minimal source_integrity_report lacking per-file SHA256 or with SHA mismatch MUST FAIL!
    forged_no_sha = {
        "checked_at": "2026-11-23T13:00:00Z",
        "status": "PASS_SOURCES_UNCHANGED",
        "entries": [
            {"source_id": "U001", "status": "UNCHANGED"},
            {"source_id": "U002", "status": "UNCHANGED"},
            {"source_id": "U003", "status": "UNCHANGED"},
        ],
    }
    res_forged = ve.validate_all(
        edl, inventory=inv, run_dir=tmp_path, validation_mode="release",
        gate_phase="C2", source_integrity_report=forged_no_sha,
    )
    assert res_forged["status"] == "FAIL_EDL_INVALID"
    assert any("SOURCE_INTEGRITY_ENTRY_INCOMPLETE" in e or "SOURCE_INTEGRITY_SHA_MISMATCH" in e for e in res_forged["errors"])

    bad_sha_rep = _valid_integrity_report(inv)
    bad_sha_rep["entries"][0]["actual_sha256"] = "0" * 64
    res_bad_sha = ve.validate_all(
        edl, inventory=inv, run_dir=tmp_path, validation_mode="release",
        gate_phase="C2", source_integrity_report=bad_sha_rep,
    )
    assert res_bad_sha["status"] == "FAIL_EDL_INVALID"
    assert any("SOURCE_INTEGRITY_SHA_MISMATCH" in e for e in res_bad_sha["errors"])

    # Valid complete per-file integrity report passes C2 release
    ok_rep = _valid_integrity_report(inv)
    res_ok = ve.validate_all(
        edl, inventory=inv, run_dir=tmp_path, validation_mode="release",
        gate_phase="C2", source_integrity_report=ok_rep,
    )
    assert res_ok["status"] == "PASS_EDL_VALID_FOR_RELEASE", res_ok["errors"]
    assert res_ok["structural_pass"] is True
    assert res_ok["source_integrity_pass"] is True
    assert res_ok["release_ready"] is True

    # R3-24: CLI exit codes — release without integrity exits 1; structural exits 0 with release_ready=False
    edl_p = tmp_path / "edl.json"
    inv_p = tmp_path / "inv.json"
    edl_p.write_text(json.dumps(edl), encoding="utf-8")
    inv_p.write_text(json.dumps(list(inv.values())), encoding="utf-8")
    assert ve.main(["--edl", str(edl_p), "--inventory", str(inv_p), "--run-dir", str(tmp_path), "--validation-mode", "release"]) == 1
    assert ve.main(["--edl", str(edl_p), "--inventory", str(inv_p), "--run-dir", str(tmp_path), "--validation-mode", "structural"]) == 0


# --- PHASE D (R3-04..R3-08): Mandatory BGM/SFX Audio & Conditional Human Checklist ---

def test_r3_04_05_06_07_08_audio_plan_bgm_sfx_and_conditional_human_checklist(tmp_path: Path) -> None:
    silent_mp4 = tmp_path / f"{FIXTURE_TAG}_silent.mp4"
    _make_unit_mp4(silent_mp4, duration_s=1.6, with_audio=False)

    # R3-04: EDL with ONLY A1_BGM and voice_policy=NONE + --allow-silent -> MUST FAIL!
    edl_bgm = {
        "voice_policy": "NONE",
        "output_spec": {"width": 320, "height": 240, "timeline_fps": "30/1"},
        "shots": [{"shot_id": "S1", "output_in_frame": 0, "output_out_frame": 48}],
        "audio_tracks": [{"clip_id": "A1", "track": "A1_BGM", "source_id": "U003"}],
    }
    res_bgm = vx.evaluate_export(silent_mp4, edl=edl_bgm, require_audio=False, qa_level="technical")
    assert res_bgm["mp4_qa_pass"] is False
    assert res_bgm["audio_signal_status"] == "FAIL_SILENT_OVERRIDE_CONFLICTS_WITH_AUDIO_PLAN"

    # R3-05: EDL with ONLY SFX / UI click cue + silent export -> MUST FAIL!
    sfx_cues = [{"cue_id": "FX1", "cue_type": "SFX_UI_CLICK", "timeline_in_s": 0.4, "timeline_out_s": 0.6}]
    res_sfx = vx.evaluate_export(silent_mp4, cue_sheet=sfx_cues, require_audio=False, qa_level="technical")
    assert res_sfx["mp4_qa_pass"] is False
    assert res_sfx["audio_signal_status"] == "FAIL_SILENT_OVERRIDE_CONFLICTS_WITH_AUDIO_PLAN"

    # R3-06: Explicitly optional & omitted audio cue in silent montage -> silent export ALLOWED!
    opt_cues = [{"cue_id": "BGM_OPT", "cue_type": "BGM", "optional": True, "explicitly_omitted": True}]
    edl_silent_montage = {
        "mode": "montage",
        "voice_policy": "NONE",
        "output_spec": {"width": 320, "height": 240, "timeline_fps": "30/1"},
        "shots": [{"shot_id": "S1", "output_in_frame": 0, "output_out_frame": 48}],
        "audio_tracks": [],
    }
    res_opt = vx.evaluate_export(silent_mp4, edl=edl_silent_montage, cue_sheet=opt_cues, require_audio=False, qa_level="technical")
    assert res_opt["mp4_qa_pass"] is True
    assert res_opt["audio_signal_status"] == "SKIPPED_SILENT_MODE"

    # R3-07: Owner checklist puts "N/A" on intelligibility for a video WITH VO -> MUST NOT PASS!
    mp4_sha = "a" * 64
    edl_vo_bgm = {
        "voice_policy": "LOCAL_KOKORO_EN_US",
        "audio_tracks": [
            {"clip_id": "VO1", "track": "A1_VO", "source_id": "U003"},
            {"clip_id": "BGM1", "track": "A2_BGM", "source_id": "U004"},
        ],
    }
    ev_na_vo = {
        "reviewer": "owner",
        "reviewer_type": "OWNER_HUMAN",
        "confirmation_source": "OWNER_INTERACTION_RECORDED",
        "reviewed_at": "2026-11-23T12:15:00Z",
        "mp4_sha256": mp4_sha,
        "playback_confirmed": True,
        "verdict": "PASS",
        "auditory_checklist": {
            "intelligibility": "N/A",
            "pops_clicks": True,
            "ducking": "N/A",
            "sync": True,
            "no_unexpected_silence": True,
        },
    }
    res_na = vx.validate_perceptual_audio_evidence(ev_na_vo, mp4_sha, edl=edl_vo_bgm, exported_at="2026-11-23T12:00:00Z")
    assert res_na["status"] == "PERCEPTUAL_AUDIO_PENDING"
    assert "CHECKLIST_NA_FORBIDDEN" in res_na["reason"]

    # R3-08: Agent self-filled OWNER_HUMAN without OWNER_INTERACTION_RECORDED OR pre-dated timestamp -> PENDING!
    ev_bot_spoof = copy.deepcopy(ev_na_vo)
    ev_bot_spoof["auditory_checklist"]["intelligibility"] = True
    ev_bot_spoof["auditory_checklist"]["ducking"] = True
    ev_bot_spoof["confirmation_source"] = "AGENT_SYNTHESIZED"
    res_spoof = vx.validate_perceptual_audio_evidence(ev_bot_spoof, mp4_sha, edl=edl_vo_bgm, exported_at="2026-11-23T12:00:00Z")
    assert res_spoof["status"] == "PERCEPTUAL_AUDIO_PENDING"
    assert res_spoof["live_human_confirmed"] is False

    ev_predated = copy.deepcopy(ev_bot_spoof)
    ev_predated["confirmation_source"] = "OWNER_INTERACTION_RECORDED"
    ev_predated["reviewed_at"] = "2026-11-23T11:00:00Z"  # BEFORE exported_at!
    res_pred = vx.validate_perceptual_audio_evidence(ev_predated, mp4_sha, edl=edl_vo_bgm, exported_at="2026-11-23T12:00:00Z")
    assert res_pred["status"] == "PERCEPTUAL_AUDIO_PENDING"
    assert "REVIEWED_BEFORE_EXPORT" in res_pred["reason"]


# --- PHASE E (R3-09..R3-14, R3-19, R3-25): Strict Timestamps, Project-ID Trace & Raw Transcript Lineage ---

def test_r3_09_to_14_19_25_mcp_timestamps_project_lineage_and_raw_transcript(tmp_path: Path) -> None:
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    proj_dir = tmp_path / "projects" / "PRJ_R3"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.concat").write_text("{}", encoding="utf-8")
    mp4 = exports_dir / f"{FIXTURE_TAG}_r3.mp4"
    _make_unit_mp4(mp4, duration_s=1.6, with_audio=True)
    prev_png = tmp_path / "prev.png"
    prev_sha = _extract_png(mp4, prev_png, 0.8)
    mp4_sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
    probe = vx.probe_export(mp4)

    trace_rows = [
        {"tool": "project_create", "call_id": "c1", "project_id": "PRJ_R3", "status": "ok", "ts": "2026-11-23T11:59:50Z"},
        {"tool": "timeline_read", "call_id": "c2", "project_id": "PRJ_R3", "status": "ok", "ts": "2026-11-23T11:59:52Z"},
        {"tool": "preview_frame", "call_id": "c3", "project_id": "PRJ_R3", "status": "ok", "ts": "2026-11-23T11:59:54Z"},
        {"tool": "project_save", "call_id": "c4", "project_id": "PRJ_R3", "status": "ok", "ts": "2026-11-23T11:59:56Z"},
        {"tool": "project_close", "call_id": "c5", "project_id": "PRJ_R3", "status": "ok", "ts": "2026-11-23T11:59:57Z"},
        {"tool": "project_open", "call_id": "c6", "project_id": "PRJ_R3", "status": "ok", "ts": "2026-11-23T11:59:58Z"},
        {"tool": "export_start", "call_id": "c7", "project_id": "PRJ_R3", "status": "ok", "ts": "2026-11-23T12:00:00Z"},
        {"tool": "export_wait", "call_id": "c8", "project_id": "PRJ_R3", "status": "ok", "ts": "2026-11-23T12:00:04Z"},
    ]
    raw_jsonl = tmp_path / "MCP_RAW_TRACE.jsonl"
    raw_jsonl.write_text("\n".join(json.dumps(r) for r in trace_rows) + "\n", encoding="utf-8")
    raw_sha = hashlib.sha256(raw_jsonl.read_bytes()).hexdigest()

    base_ev = {
        "evidence_source": "LIVE_MCP_EXPORT_EVIDENCE",
        "project_id": "PRJ_R3",
        "project_path": str(proj_dir),
        "allowed_project_root": str(tmp_path / "projects"),
        "run_id": "RUN_R3",
        "concat_binary": "/Applications/Concat.app/Contents/MacOS/concat",
        "concat_binary_sha256": "1" * 64,
        "concat_version": "0.2.12",
        "mcp_mode": "headless",
        "export_start": {"job_id": "J1", "status": "started", "started_at": "2026-11-23T12:00:00Z"},
        "export_wait": {"job_id": "J1", "status": "completed", "exit_ok": True, "completed_at": "2026-11-23T12:00:04Z"},
        "reopen_verified": True,
        "timeline_fingerprint": "fp_r3",
        "timeline_fingerprint_before_save": "fp_r3",
        "timeline_fingerprint_after_reopen": "fp_r3",
        "tool_trace": trace_rows,
        "raw_transcript_path": str(raw_jsonl),
        "raw_transcript_sha256": raw_sha,
        "output_path": str(mp4),
        "allowed_export_root": str(exports_dir),
        "sha256": mp4_sha,
        "exported_at": "2026-11-23T12:00:05Z",
    }
    previews = [{"path": str(prev_png), "timestamp_s": 0.8, "origin": "CONCAT_MCP_PREVIEW_FRAME", "tool_call_id": "c3", "sha256": prev_sha}]
    owner_ev = {
        "reviewer": "owner",
        "reviewer_type": "OWNER_HUMAN",
        "confirmation_source": "OWNER_INTERACTION_RECORDED",
        "reviewed_at": "2026-11-23T12:05:00Z",
        "mp4_sha256": mp4_sha,
        "playback_confirmed": True,
        "verdict": "PASS",
        "auditory_checklist": {"intelligibility": True, "pops_clicks": True, "ducking": True, "sync": True, "no_unexpected_silence": True},
    }

    # R3-09: Missing export_start.started_at or export_wait.completed_at -> MUST FAIL!
    no_ts = copy.deepcopy(base_ev)
    del no_ts["export_start"]["started_at"]
    res_nots = vx.validate_mcp_export_provenance(no_ts, probe)
    assert res_nots["status"] == "FAIL_MCP_PROVENANCE"
    assert any("MISSING_TIMESTAMP" in e for e in res_nots["errors"])

    # R3-10: Mismatched project_id inside tool_trace step -> MUST FAIL!
    bad_proj_trace = copy.deepcopy(base_ev)
    bad_proj_trace["tool_trace"][6]["project_id"] = "PRJ_OTHER"
    res_bp = vx.validate_mcp_export_provenance(bad_proj_trace, probe)
    assert res_bp["status"] == "FAIL_MCP_PROVENANCE"
    assert any("TRACE_PROJECT_ID_MISMATCH" in e for e in res_bp["errors"])

    # R3-11 / R3-12: Self-authored JSON WITHOUT raw_transcript_path -> SCHEMA_ONLY_UNATTESTED, live_concat_verified=False, production_release_pass=False!
    no_raw = copy.deepcopy(base_ev)
    del no_raw["raw_transcript_path"]
    del no_raw["raw_transcript_sha256"]
    res_noraw = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C1", release_policy="full-creative",
        preview_checks=previews, mcp_export_evidence=no_raw, perceptual_audio_evidence=owner_ev,
    )
    assert res_noraw["live_concat_verified"] is False
    assert res_noraw["production_release_pass"] is False
    assert res_noraw["mcp_provenance"]["evidence_trust_level"] == "SCHEMA_ONLY_UNATTESTED"

    # R3-13: UNIT_SIMULATED_PROVENANCE NEVER sets production_release_pass=True even with transcript!
    sim_ev = copy.deepcopy(base_ev)
    sim_ev["evidence_source"] = "UNIT_SIMULATED_PROVENANCE"
    res_sim = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C1", release_policy="full-creative",
        preview_checks=previews, mcp_export_evidence=sim_ev, perceptual_audio_evidence=owner_ev,
    )
    assert res_sim["live_concat_verified"] is False
    assert res_sim["production_release_pass"] is False

    # R3-14 / R3-19: Technical QA diagnostic on valid synthetic MP4 -> PASS_TECHNICAL_ONLY, release_gate_pass=False
    res_tech = vx.evaluate_export(mp4, qa_level="technical", require_audio=True)
    assert res_tech["overall_status"] == "PASS_TECHNICAL_ONLY"
    assert res_tech["release_gate_pass"] is False
    assert res_tech["production_release_pass"] is False


# --- PHASE F (R3-15): Multi-Root Source Integrity Path & Duplicate Hardening ---

def test_r3_15_verify_source_hashes_blocks_backslash_symlink_nonregular_and_duplicates(tmp_path: Path) -> None:
    root = tmp_path / "r1"
    root.mkdir()
    real_file = root / "clip.mp4"
    real_file.write_bytes(b"abc")
    sha = hashlib.sha256(b"abc").hexdigest()

    # Subdirectory disguised as source file (non-regular file)
    sub = root / "fake_dir.mp4"
    sub.mkdir()

    # Symlink to outside file
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"secret")
    (root / "sym.mp4").symlink_to(outside)

    records = [
        {"source_id": "U001", "root_id": "R01", "relative_label": r"R01/..\..\outside.mp4", "sha256": sha},
        {"source_id": "U002", "root_id": "R01", "relative_label": "R01/sym.mp4", "sha256": sha},
        {"source_id": "U003", "root_id": "R01", "relative_label": "R01/fake_dir.mp4", "sha256": sha},
        {"source_id": "U004", "root_id": "R01", "relative_label": "R01/clip.mp4", "sha256": sha},
        {"source_id": "U004", "root_id": "R01", "relative_label": "R01/clip.mp4", "sha256": sha},
    ]
    res = vsh.verify_unchanged(records, root_map={"R01": root})
    assert res["status"] == "FAIL_SOURCE_DRIFT_OR_MISSING"
    reasons = {d.get("reason") for d in res["drifted"]}
    assert "PATH_ESCAPE_REJECTED" in reasons
    assert "SYMLINK_REJECTED" in reasons
    assert "NOT_A_REGULAR_FILE" in reasons
    assert "DUPLICATE_MANIFEST_SOURCE_ID" in reasons


# --- PHASE F (R3-16, R3-17, R3-18): Bounded Scanner, Determinism, Multi-Root Unicode Contact Sheets ---

def test_r3_16_17_18_scanner_incomplete_determinism_and_unicode_contact_sheets(tmp_path: Path) -> None:
    r1 = tmp_path / "root_one"
    r2 = tmp_path / "root_two"
    r1.mkdir()
    r2.mkdir()
    # Vietnamese Unicode filename with spaces and quotes in both roots (same basename, distinct content)
    fname = "Cảnh 'đẹp' 01.mp4"
    f1 = r1 / fname
    f2 = r2 / fname
    _make_unit_mp4(f1, duration_s=1.0, with_audio=False)
    _make_unit_mp4(f2, duration_s=1.4, with_audio=True)
    # Extra valid tiny clips to trigger MAX_FILES / MAX_ENTRIES budget cleanly
    for i in range(4):
        shutil.copy2(f1, r1 / f"extra_{i}.mp4")

    # R3-16: Budget cap produces INCOMPLETE_SOURCE_INVENTORY and exit 2
    out_inc = tmp_path / "inc.csv"
    rc_inc = ps.main([str(r1), "--out-csv", str(out_inc), "--max-files", "2"])
    assert rc_inc == 2
    det_entries = ps.discover_inputs_detailed([r1], limits={"max_entries_scanned": 2})
    assert det_entries["scan_complete"] is False
    assert any("MAX_ENTRIES" in r for r in det_entries["incomplete_reasons"])
    det_wall = ps.discover_inputs_detailed([r1], limits={"max_wallclock_s": 0.0})
    assert det_wall["scan_complete"] is False
    assert any("MAX_WALLCLOCK" in r for r in det_wall["incomplete_reasons"])

    # R3-17 & R3-18: Complete multi-root scan deterministic across worker counts & unique contact sheets
    cs1 = tmp_path / "cs_run1"
    cs2 = tmp_path / "cs_run2"
    j1 = tmp_path / "inv1.json"
    j2 = tmp_path / "inv2.json"
    assert ps.main([str(r1 / fname), str(r2 / fname), "--out-csv", str(tmp_path / "inv1.csv"), "--out-json", str(j1), "--contact-dir", str(cs1), "--workers", "1"]) == 0
    assert ps.main([str(r1 / fname), str(r2 / fname), "--out-csv", str(tmp_path / "inv2.csv"), "--out-json", str(j2), "--contact-dir", str(cs2), "--workers", "4"]) == 0

    rows1 = json.loads(j1.read_text(encoding="utf-8"))
    rows2 = json.loads(j2.read_text(encoding="utf-8"))
    key_fields = ("source_id", "root_id", "relative_label", "sha256", "bytes")
    assert [{k: r[k] for k in key_fields} for r in rows1] == [{k: r[k] for k in key_fields} for r in rows2]
    assert len(rows1) == 2
    assert rows1[0]["root_id"] != rows1[1]["root_id"]
    stills_all = sorted(p.name for p in cs1.glob("*.jpg"))
    assert len(stills_all) >= 4  # both distinct roots produced non-colliding stills
    assert any(n.startswith("U001_") for n in stills_all)
    assert any(n.startswith("U002_") for n in stills_all)


# --- PHASE G/D/F/I (R3-20, R3-21, R3-22, R3-23, R3-25 + Subprocess CLI Contract) ---

def test_r3_20_21_22_23_25_env_tools_mutation_package_and_cli_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # R3-20: Unavailable Concat binary reports BLOCKED_ENV_CONCAT_BINARY_MISSING, never MCP_CONNECTED
    monkeypatch.setattr(pa, "_disk_usage_gb", lambda _p: (80.0, 500.0))
    monkeypatch.setattr(
        pa,
        "discover_concat_binary",
        lambda profile, explicit_binary=None, env=None, source_checkouts=None: {
            "binary_status": "BINARY_BLOCKED_NOT_FOUND",
            "binary_source": "NOT_FOUND",
            "app_binary": "NOT_FOUND",
            "app_arch": "UNKNOWN",
            "app_version": "NOT_INSTALLED",
            "app_sha256": None,
        },
    )
    env_probe = pa.probe_host_environment(system="Darwin", machine="arm64", os_version="14.4.1")
    assert env_probe["binary_status"] == "BINARY_BLOCKED_NOT_FOUND"
    assert env_probe["c0_status"] == "BLOCKED_ENV_CONCAT_BINARY_MISSING"
    assert env_probe["c0_ready_for_mcp"] is False
    assert env_probe["mcp_handshake_status"] not in {"MCP_CONNECTED", "PASS_C0_MCP_CONNECTED"}

    # R3-21: Missing ffmpeg produces BLOCKED_ENV_FFMPEG_MISSING / MEASUREMENT_INCOMPLETE, never PASS_AUDIO_SIGNAL
    mp4 = tmp_path / f"{FIXTURE_TAG}_aud.mp4"
    _make_unit_mp4(mp4, duration_s=1.5, with_audio=True)
    orig_which = shutil.which
    monkeypatch.setattr(vx.shutil, "which", lambda name: None if name == "ffmpeg" else orig_which(name))
    sig_missing = vx.measure_audio_segments(mp4)
    assert sig_missing["audio_signal_status"] == "BLOCKED_ENV_FFMPEG_MISSING"
    res_no_ffmpeg = vx.evaluate_export(mp4, qa_level="technical", require_audio=True)
    assert res_no_ffmpeg["audio_signal_status"] != "PASS_AUDIO_SIGNAL"
    assert res_no_ffmpeg["mp4_qa_pass"] is False
    monkeypatch.setattr(vx.shutil, "which", orig_which)

    # R3-22: Source hash before == after passes, byte mutation fails closed
    sroot = tmp_path / "orig_src"
    sroot.mkdir()
    orig = sroot / "hero.mp4"
    orig.write_bytes(b"original-video-bytes-12345")
    orig_sha = hashlib.sha256(orig.read_bytes()).hexdigest()
    rec = [{"source_id": "U001", "root_id": "R01", "relative_label": "R01/hero.mp4", "sha256": orig_sha}]
    assert vsh.verify_unchanged(rec, root_map={"R01": sroot})["status"] == "PASS_SOURCES_UNCHANGED"
    orig.write_bytes(b"MUTATED-video-bytes-99999")
    mut_res = vsh.verify_unchanged(rec, root_map={"R01": sroot})
    assert mut_res["status"] == "FAIL_SOURCE_DRIFT_OR_MISSING"
    assert mut_res["drifted"][0]["status"] == "DRIFT_DETECTED"
    assert mut_res["drifted"][0]["actual_sha256"] != orig_sha

    # R3-23: check_skill_package detects bad hash, duplicate manifest entries, symlink, traversal & secret leak
    fake_pkg = tmp_path / "pkg"
    fake_pkg.mkdir()
    (fake_pkg / "SKILL.md").write_text("---\nname: video-director-concat\ndescription: Concat MCP cross-platform video director on macOS and Windows.\n---\nNever claim a final exported video until Concat completes. CapCut excluded. platform_macos.md platform_windows.md\n", encoding="utf-8")
    fake_tok = "sk" + "-" + "1234567890" + "ABCDEFGHIJKLMN"
    fake_user_path = "/Users" + "/" + "alice" + "/secret/"
    (fake_pkg / "leak.md").write_text(f"token {fake_tok} path {fake_user_path}\n", encoding="utf-8")
    (fake_pkg / "sym.txt").symlink_to(orig)
    bad_manifest = fake_pkg / "MANIFEST.json"
    bad_manifest.write_text(json.dumps({
        "name": "video-director-concat",
        "skill_semver": "0.0.1",
        "file_count": 3,
        "files": [
            {"path": "SKILL.md", "bytes": 1, "sha256": "0" * 64},
            {"path": "SKILL.md", "bytes": 1, "sha256": "0" * 64},
            {"path": "../escape.txt", "bytes": 1, "sha256": "0" * 64},
        ],
    }), encoding="utf-8")
    m_res = csp.validate_manifest_hashes(fake_pkg, bad_manifest)
    assert m_res["status"] == "FAIL"
    joined_m = " ".join(m_res["errors"])
    assert "SHA256_MISMATCH" in joined_m
    assert "DUPLICATE_MANIFEST_ENTRY" in joined_m
    assert "UNSAFE_MANIFEST_PATH" in joined_m
    assert "SYMLINK" in joined_m
    sec_res = csp.scan_for_secrets_and_hardcoded_user_paths(fake_pkg)
    assert sec_res["status"] == "FAIL"
    assert any("SECRET_PATTERN_DETECTED" in f for f in sec_res["findings"])
    assert any("HARDCODED_USER_PATH" in f for f in sec_res["findings"])

    # R3-25: Replayed trace with mismatched SHA, interrupted export, and lock conflict -> FAIL_MCP_PROVENANCE
    probe = vx.probe_export(mp4)
    proj_dir = tmp_path / "p25"
    proj_dir.mkdir()
    (proj_dir / "project.concat").write_text("{}", encoding="utf-8")
    (proj_dir / "concat.lock").write_text("locked", encoding="utf-8")
    broken_ev = {
        "evidence_source": "LIVE_MCP_EXPORT_EVIDENCE",
        "project_id": "PRJ25",
        "project_path": str(proj_dir),
        "allowed_project_root": str(tmp_path),
        "run_id": "RUN_REPLAY",
        "concat_binary": "/Applications/Concat.app/Contents/MacOS/concat",
        "concat_binary_sha256": "1" * 64,
        "concat_version": "0.2.12",
        "mcp_mode": "headless",
        "export_start": {"job_id": "J25", "status": "started", "started_at": "2026-11-23T12:00:00Z"},
        "export_wait": {"job_id": "J25", "status": "interrupted", "exit_ok": False, "completed_at": "2026-11-23T11:59:00Z"},
        "reopen_verified": False,
        "output_path": str(mp4),
        "allowed_export_root": str(tmp_path),
        "sha256": "f" * 64,  # deliberately mismatched
        "exported_at": "2026-11-23T12:00:05Z",
        "tool_trace": [],
    }
    prov_bad = vx.validate_mcp_export_provenance(broken_ev, probe, expected_run_id="RUN_NEW")
    assert prov_bad["status"] == "FAIL_MCP_PROVENANCE"
    assert prov_bad["live_evidence_eligible"] is False
    errs = " ".join(prov_bad["errors"])
    assert "SHA256_MISMATCH" in errs
    assert "RUN_ID_MISMATCH" in errs
    assert "EXPORT_WAIT_NOT_COMPLETED" in errs

    # High-level CLI subprocess contract test (B1 requirement: unit + CLI layer)
    proc_ve = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "verify_export.py"), "--mp4", str(mp4), "--qa-level", "release"],
        capture_output=True, text=True, check=False,
    )
    assert proc_ve.returncode == 1
    out_ve = json.loads(proc_ve.stdout)
    assert out_ve["production_release_pass"] is False
    assert out_ve["release_gate_pass"] is False
    assert out_ve["live_concat_verified"] is False
