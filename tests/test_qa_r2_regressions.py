"""QA.R2 Bug Reproduction & Comprehensive Regression Suite (R2-01 through R2-32).

All generated media fixtures in this file are strictly:
  UNIT_SYNTHETIC_FFMPEG_FIXTURE_NOT_CONCAT_EXPORT
and test validator/scanner semantics only — never treated as live Concat exports.
"""

from __future__ import annotations

import copy
import csv
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


def _make_unit_mp4(
    dest: Path,
    duration_s: float = 2.0,
    audio_filter: str = "volume=-16dB",
    static_color: str | None = None,
    with_audio: bool = True,
) -> None:
    """Create a clearly tagged synthetic FFmpeg fixture for unit testing QA validators only."""
    ffmpeg_bin = _ffmpeg_or_skip()
    v_in = (
        f"color=c={static_color}:s=320x240:d={duration_s}:r=30"
        if static_color
        else f"testsrc2=duration={duration_s}:size=320x240:rate=30"
    )
    cmd = [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", v_in]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_s}", "-af", audio_filter, "-c:a", "aac", "-shortest"]
    else:
        cmd += ["-an"]
    cmd += ["-pix_fmt", "yuv420p", "-y", str(dest)]
    subprocess.run(cmd, check=True)


def _extract_png(mp4: Path, png: Path, t_s: float = 1.0) -> str:
    subprocess.run(
        [_ffmpeg_or_skip(), "-hide_banner", "-loglevel", "error", "-ss", str(t_s), "-i", str(mp4), "-frames:v", "1", "-y", str(png)],
        check=True,
    )
    return hashlib.sha256(png.read_bytes()).hexdigest()


def _build_live_like_provenance(
    tmp_path: Path,
    exports_dir: Path,
    mp4: Path,
    prev_png: Path,
    prev_sha: str,
    evidence_source: str = "LIVE_MCP_EXPORT_EVIDENCE",
    preview_origin: str = "CONCAT_MCP_PREVIEW_FRAME",
) -> tuple[dict, list[dict]]:
    proj_dir = tmp_path / "projects" / "PRJ_R2_01"
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "project.concat").write_text("{}", encoding="utf-8")
    mp4_sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
    trace_rows = [
        {"tool": "project_create", "call_id": "c1", "project_id": "PRJ_R2_01", "status": "ok", "ts": "2026-11-23T11:59:50Z"},
        {"tool": "timeline_read", "call_id": "c2", "project_id": "PRJ_R2_01", "status": "ok", "ts": "2026-11-23T11:59:52Z"},
        {"tool": "preview_frame", "call_id": "c3", "project_id": "PRJ_R2_01", "status": "ok", "ts": "2026-11-23T11:59:54Z"},
        {"tool": "project_save", "call_id": "c4", "project_id": "PRJ_R2_01", "status": "ok", "ts": "2026-11-23T11:59:56Z"},
        {"tool": "project_close", "call_id": "c5", "project_id": "PRJ_R2_01", "status": "ok", "ts": "2026-11-23T11:59:57Z"},
        {"tool": "project_open", "call_id": "c6", "project_id": "PRJ_R2_01", "status": "ok", "ts": "2026-11-23T11:59:58Z"},
        {"tool": "export_start", "call_id": "c7", "project_id": "PRJ_R2_01", "status": "ok", "ts": "2026-11-23T12:00:00Z"},
        {"tool": "export_wait", "call_id": "c8", "project_id": "PRJ_R2_01", "status": "ok", "ts": "2026-11-23T12:00:05Z"},
    ]
    raw_jsonl = tmp_path / "MCP_RAW_TRACE.jsonl"
    raw_jsonl.write_text("\n".join(json.dumps(r) for r in trace_rows) + "\n", encoding="utf-8")
    raw_sha = hashlib.sha256(raw_jsonl.read_bytes()).hexdigest()
    mcp_ev = {
        "evidence_source": evidence_source,
        "project_id": "PRJ_R2_01",
        "project_path": str(proj_dir),
        "allowed_project_root": str(tmp_path / "projects"),
        "run_id": "RUN_R2_01",
        "concat_binary": "/Applications/Concat.app/Contents/MacOS/concat",
        "concat_binary_sha256": "1" * 64,
        "concat_version": "0.2.12",
        "mcp_mode": "headless",
        "export_start": {"job_id": "JOB_R2_01", "status": "started", "started_at": "2026-11-23T12:00:00Z"},
        "export_wait": {"job_id": "JOB_R2_01", "status": "completed", "exit_ok": True, "completed_at": "2026-11-23T12:00:05Z"},
        "reopen_verified": True,
        "timeline_fingerprint": "fp_r2_exact",
        "timeline_fingerprint_before_save": "fp_r2_exact",
        "timeline_fingerprint_after_reopen": "fp_r2_exact",
        "tool_trace": trace_rows,
        "raw_transcript_path": str(raw_jsonl),
        "raw_transcript_sha256": raw_sha,
        "output_path": str(mp4),
        "allowed_export_root": str(exports_dir),
        "sha256": mp4_sha,
        "exported_at": "2026-11-23T12:00:06Z",
    }
    previews = [
        {
            "path": str(prev_png),
            "timestamp_s": 1.0,
            "origin": preview_origin,
            "tool_call_id": "c3",
            "sha256": prev_sha,
        }
    ]
    return mcp_ev, previews


def _valid_owner_listening(mp4_sha: str) -> dict:
    return {
        "reviewer": "machine_owner",
        "reviewer_type": "OWNER_HUMAN",
        "confirmation_source": "OWNER_INTERACTION_RECORDED",
        "reviewed_at": "2026-11-23T12:10:00Z",
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


# --- P0-A & P1-G (R2-01..R2-06, R2-29): Provenance, Job ID, Preview Origin & Live vs Unit Separation ---

def test_p0_a_p1_g_r2_01_to_06_live_provenance_and_adversarial_checks(tmp_path: Path) -> None:
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    mp4 = exports_dir / f"{FIXTURE_TAG}.mp4"
    _make_unit_mp4(mp4, duration_s=2.0)
    prev_png = tmp_path / "prev_1.0.png"
    prev_sha = _extract_png(mp4, prev_png, 1.0)
    mp4_sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
    owner_ev = _valid_owner_listening(mp4_sha)

    # R2-01 / R2-29: UNIT_SIMULATED_PROVENANCE can NEVER yield live_concat_verified=True or PASS_END_TO_END_EXPORT_QA!
    sim_ev, sim_previews = _build_live_like_provenance(
        tmp_path, exports_dir, mp4, prev_png, prev_sha,
        evidence_source="UNIT_SIMULATED_PROVENANCE",
    )
    r_sim = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C1", release_policy="full-creative",
        preview_checks=sim_previews, mcp_export_evidence=sim_ev, perceptual_audio_evidence=owner_ev,
    )
    assert r_sim["live_concat_verified"] is False
    assert r_sim["overall_status"] != "PASS_END_TO_END_EXPORT_QA"
    assert r_sim["release_gate_pass"] is False

    # R2-02: Missing export_wait.job_id MUST fail (no silent bypass!)
    live_ev, live_previews = _build_live_like_provenance(tmp_path, exports_dir, mp4, prev_png, prev_sha)
    no_wait_job = copy.deepcopy(live_ev)
    del no_wait_job["export_wait"]["job_id"]
    p_res = vx.validate_mcp_export_provenance(no_wait_job, vx.probe_export(mp4))
    assert p_res["status"] == "FAIL_MCP_PROVENANCE"
    assert any("MISSING_EXPORT_WAIT_JOB_ID" in e for e in p_res["errors"])

    # R2-03: Mismatched job_ids MUST fail
    bad_job = copy.deepcopy(live_ev)
    bad_job["export_wait"]["job_id"] = "JOB_OTHER"
    assert vx.validate_mcp_export_provenance(bad_job, vx.probe_export(mp4))["status"] == "FAIL_MCP_PROVENANCE"

    # R2-04: Stale run_id / project_id reused across runs MUST fail when expected_run_id/expected_project_id given
    stale_res = vx.validate_mcp_export_provenance(
        live_ev, vx.probe_export(mp4), expected_run_id="RUN_NEW_99", expected_project_id="PRJ_NEW_99"
    )
    assert stale_res["status"] == "FAIL_MCP_PROVENANCE"
    assert any("RUN_ID_MISMATCH" in e for e in stale_res["errors"])

    # R2-05: Timeline fingerprint mismatch before save vs after reopen MUST fail
    bad_fp = copy.deepcopy(live_ev)
    bad_fp["timeline_fingerprint_after_reopen"] = "fp_drifted"
    assert vx.validate_mcp_export_provenance(bad_fp, vx.probe_export(mp4))["status"] == "FAIL_MCP_PROVENANCE"

    # Missing required live tool trace steps MUST fail
    bad_trace = copy.deepcopy(live_ev)
    bad_trace["tool_trace"] = [{"tool": "project_create", "call_id": "c1", "status": "ok", "ts": "2026-11-23T12:00:00Z"}]
    assert vx.validate_mcp_export_provenance(bad_trace, vx.probe_export(mp4))["status"] == "FAIL_MCP_PROVENANCE"

    # Inverted timestamps (export_wait before export_start) MUST fail
    bad_ts = copy.deepcopy(live_ev)
    bad_ts["export_start"]["started_at"] = "2026-11-23T12:10:00Z"
    bad_ts["export_wait"]["completed_at"] = "2026-11-23T12:00:00Z"
    assert vx.validate_mcp_export_provenance(bad_ts, vx.probe_export(mp4))["status"] == "FAIL_MCP_PROVENANCE"

    # Symlink escape in export output_path MUST fail
    outside_mp4 = tmp_path / "outside.mp4"
    shutil.copy2(mp4, outside_mp4)
    sym_mp4 = exports_dir / "symlink_export.mp4"
    sym_mp4.symlink_to(outside_mp4)
    sym_ev = copy.deepcopy(live_ev)
    sym_ev["output_path"] = str(sym_mp4)
    assert vx.validate_mcp_export_provenance(sym_ev, vx.probe_export(sym_mp4))["status"] == "FAIL_MCP_PROVENANCE"

    # R2-06: Preview derived from MP4 (not CONCAT_MCP_PREVIEW_FRAME) MUST be rejected in live release!
    fake_prev = copy.deepcopy(live_previews)
    fake_prev[0]["origin"] = "FFMPEG_EXTRACTED_FROM_MP4"
    r_fake_prev = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C1", release_policy="full-creative",
        preview_checks=fake_prev, mcp_export_evidence=live_ev, perceptual_audio_evidence=owner_ev,
    )
    assert r_fake_prev["release_gate_pass"] is False
    assert any("PREVIEW_ORIGIN_NOT_CONCAT_MCP" in b for b in r_fake_prev["release_blockers"])


# --- P0-B & P0-C (R2-07..R2-10): Audio Human Gate, C1 vs C2 Boundaries & Silent Override ---

def test_p0_b_p0_c_r2_07_to_10_human_audio_gate_and_c1_c2_boundaries(tmp_path: Path) -> None:
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    mp4 = exports_dir / f"{FIXTURE_TAG}_audio_gate.mp4"
    _make_unit_mp4(mp4, duration_s=2.0)
    prev_png = tmp_path / "prev.png"
    prev_sha = _extract_png(mp4, prev_png, 1.0)
    mp4_sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
    live_ev, live_previews = _build_live_like_provenance(tmp_path, exports_dir, mp4, prev_png, prev_sha)

    # R2-07 / R2-08: C2 with technical-smoke policy MUST HARD-FAIL!
    r_c2_bad = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C2", release_policy="technical-smoke",
        preview_checks=live_previews, mcp_export_evidence=live_ev,
    )
    assert r_c2_bad["release_gate_pass"] is False
    assert r_c2_bad["creative_release_gate_pass"] is False
    assert any("INVALID_RELEASE_POLICY_FOR_PHASE" in b for b in r_c2_bad["release_blockers"])

    # R2-08: C1 technical-smoke sets technical_e2e_gate_pass=True but creative_release_gate_pass=False & release_gate_pass=False!
    r_c1_tech = vx.evaluate_export(
        mp4, qa_level="release", gate_phase="C1", release_policy="technical-smoke",
        preview_checks=live_previews, mcp_export_evidence=live_ev,
    )
    assert r_c1_tech["overall_status"] == "C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING"
    assert r_c1_tech["technical_e2e_gate_pass"] is True
    assert r_c1_tech["creative_release_gate_pass"] is False
    assert r_c1_tech["release_gate_pass"] is False

    # R2-09: Agent/bot self-created perceptual audio dict MUST stay PERCEPTUAL_AUDIO_PENDING!
    bot_ev = {
        "reviewer": "qa_listener",
        "reviewer_type": "AGENT",
        "reviewed_at": "2026-11-23T12:10:00Z",
        "mp4_sha256": mp4_sha,
        "playback_confirmed": True,
        "verdict": "PASS",
    }
    assert vx.validate_perceptual_audio_evidence(bot_ev, mp4_sha)["status"] == "PERCEPTUAL_AUDIO_PENDING"

    # Missing reviewer_type or missing checklist MUST stay PERCEPTUAL_AUDIO_PENDING
    incomplete_ev = {"reviewer": "owner", "reviewed_at": "2026-11-23T12:10:00Z", "mp4_sha256": mp4_sha, "verdict": "PASS"}
    assert vx.validate_perceptual_audio_evidence(incomplete_ev, mp4_sha)["status"] == "PERCEPTUAL_AUDIO_PENDING"

    # R2-10: Mismatched MP4 SHA in owner listening evidence MUST NOT pass
    bad_sha_ev = _valid_owner_listening("0" * 64)
    assert vx.validate_perceptual_audio_evidence(bad_sha_ev, mp4_sha)["status"] == "PERCEPTUAL_AUDIO_PENDING"

    # Valid OWNER_HUMAN evidence with full auditory checklist passes
    ok_owner = _valid_owner_listening(mp4_sha)
    assert vx.validate_perceptual_audio_evidence(ok_owner, mp4_sha)["status"] == "PASS_AUDIO_PERCEPTUAL"

    # Silent override conflicting with EDL voice_policy requiring VO MUST fail
    edl_vo = {
        "voice_policy": "LOCAL_KOKORO_EN_US",
        "output_spec": {"width": 320, "height": 240, "timeline_fps": "30/1"},
        "shots": [{"shot_id": "S1", "output_in_frame": 0, "output_out_frame": 60}],
        "audio_tracks": [{"clip_id": "VO1", "track": "A1_VO", "source_id": "U003"}],
    }
    r_silent_conflict = vx.evaluate_export(mp4, edl=edl_vo, require_audio=False, qa_level="technical")
    assert r_silent_conflict["mp4_qa_pass"] is False
    assert r_silent_conflict["audio_signal_status"] == "FAIL_SILENT_OVERRIDE_CONFLICTS_WITH_AUDIO_PLAN"


# --- P1-A & P1-B (R2-13..R2-17): True Streaming Scanner & Incomplete Inventory Gate ---

def test_p1_a_p1_b_r2_13_to_17_true_streaming_scandir_and_incomplete_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # R2-13: Monkeypatch os.scandir with an iterator that explodes if >25 next() calls happen!
    # Old `sorted(it)` consumed the entire iterator before max_entries; streaming must stop early!
    class _ExplodingEntry:
        def __init__(self, idx: int, base: Path) -> None:
            self.name = f"clip_{idx:05d}.mp4"
            self.path = str(base / self.name)
        def is_symlink(self) -> bool:
            return False
        def is_dir(self, follow_symlinks: bool = False) -> bool:
            return False
        def is_file(self, follow_symlinks: bool = False) -> bool:
            return True

    class _BoundedTrapScandir:
        def __init__(self, base: Path) -> None:
            self.base = base
            self.calls = 0
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def __iter__(self):
            return self
        def __next__(self):
            self.calls += 1
            if self.calls > 25:
                raise AssertionError("STREAMING_VIOLATION: iterated beyond bounded max_entries!")
            return _ExplodingEntry(self.calls, self.base)

    trap_dir = tmp_path / "huge_virtual"
    trap_dir.mkdir()
    for i in range(1, 15):
        (trap_dir / f"clip_{i:05d}.mp4").write_bytes(b"x")
    trap = _BoundedTrapScandir(trap_dir)
    monkeypatch.setattr(ps.os, "scandir", lambda _p: trap)

    res = ps.discover_inputs_detailed([str(trap_dir)], limits={"max_entries_scanned": 10, "max_files": 50})
    assert trap.calls <= 12
    assert res["scan_complete"] is False
    assert any("MAX_ENTRIES" in r for r in res["incomplete_reasons"])

    # R2-14: Real CLI budget hit MUST exit non-zero and mark INCOMPLETE_SOURCE_INVENTORY
    monkeypatch.undo()
    real_dir = tmp_path / "budget_dir"
    real_dir.mkdir()
    for i in range(6):
        _make_unit_mp4(real_dir / f"c{i}.mp4", duration_s=0.6)
    out_csv = tmp_path / "partial.csv"
    rc = ps.main([str(real_dir), "--out-csv", str(out_csv), "--max-files", "2", "--rights-tag", "OWNED", "--workers", "1"])
    assert rc != 0
    assert out_csv.exists()  # partial inventory written for inspection

    # R2-17: Workers 1, 2, 4 produce identical CSV on complete scan
    comp_dir = tmp_path / "complete_dir"
    comp_dir.mkdir()
    _make_unit_mp4(comp_dir / "b.mp4", duration_s=0.8)
    _make_unit_mp4(comp_dir / "a.mp4", duration_s=0.8)
    outputs = []
    for w in ("1", "2", "4"):
        c_csv = tmp_path / f"w{w}.csv"
        assert ps.main([str(comp_dir), "--out-csv", str(c_csv), "--rights-tag", "OWNED", "--workers", w]) == 0
        outputs.append(c_csv.read_text(encoding="utf-8"))
    assert outputs[0] == outputs[1] == outputs[2]


# --- P1-C (R2-11, R2-12, R2-25): Strict Audio Dropouts, EOF Silence & Incomplete EBU R128 ---

def test_p1_c_r2_11_12_25_audio_dropouts_eof_silence_and_missing_ebur128(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # R2-11 / R2-25: Video with 1s tone followed by 2.5s trailing EOF silence -> MUST fail unexpected dropout!
    dropout_mp4 = tmp_path / f"{FIXTURE_TAG}_eof_dropout.mp4"
    _make_unit_mp4(dropout_mp4, duration_s=3.5, audio_filter="volume='if(lt(t,1.0),0.2,0.0)':eval=frame")
    res_drop = vx.measure_audio_segments(dropout_mp4, require_audio=True)
    assert res_drop["audio_signal_status"] == "FAIL_UNEXPECTED_AUDIO_DROPOUT"
    assert len(res_drop["unexpected_silence_dropouts"]) >= 1

    # Same clip WITH explicit planned silence cue covering 1.0..3.5s -> SILENCE_PLANNED / PASS_AUDIO_SIGNAL!
    planned_cues = [{"cue_id": "GAP1", "cue_type": "INTENTIONAL_SILENCE", "timeline_in_s": 0.9, "timeline_out_s": 3.6}]
    res_planned = vx.measure_audio_segments(dropout_mp4, cue_sheet=planned_cues, require_audio=True)
    assert res_planned["audio_signal_status"] == "PASS_AUDIO_SIGNAL"
    assert len(res_planned["planned_silences"]) >= 1

    # R2-12: If ebur128 yields no parseable LUFS/true peak when required -> MEASUREMENT_INCOMPLETE (NEVER PASS!)
    clean_mp4 = tmp_path / f"{FIXTURE_TAG}_clean_audio.mp4"
    _make_unit_mp4(clean_mp4, duration_s=2.0)
    real_run = subprocess.run

    def _break_ebur128(cmd, *args, **kwargs):
        if any("ebur128" in str(c) for c in cmd):
            return subprocess.CompletedProcess(cmd, 0, "", "no summary here")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(vx.subprocess, "run", _break_ebur128)
    res_inc = vx.measure_audio_segments(clean_mp4, require_audio=True, require_lufs_and_peak=True)
    assert res_inc["audio_signal_status"] == "MEASUREMENT_INCOMPLETE"


# --- P1-D, P1-E, P1-F (R2-18..R2-23): Duplicate IDs, run_dir Requirement, Anchors, Backslash Traversal & Source Integrity ---

def test_p1_d_e_f_r2_18_to_23_duplicates_run_dir_anchors_and_windows_traversal(tmp_path: Path) -> None:
    # R2-18: Duplicate source_id in SOURCE_INVENTORY.csv MUST NOT silently overwrite
    dup_inv = tmp_path / "dup_inv.csv"
    dup_inv.write_text(
        "source_id,relative_label,media_type,rights_tag,sha256,duration_s,width,height,probe_status\n"
        f"U001,a.mp4,video,OWNED,{'a'*64},5.0,1080,1920,OK\n"
        f"U001,b.mp4,video,ANALYSIS_ONLY,{'b'*64},5.0,1080,1920,OK\n",
        encoding="utf-8",
    )
    _, inv_errs = ve.load_inventory_checked(dup_inv)
    assert any("DUPLICATE_INVENTORY_SOURCE_ID" in e for e in inv_errs)

    # R2-19: Duplicate asset_id in LICENSE_LEDGER.csv MUST NOT silently overwrite
    dup_led = tmp_path / "dup_led.csv"
    dup_led.write_text(
        "asset_id,decision,commercial_use_allowed,license_url,license_evidence_path\n"
        "LIC1,REJECTED,NO,https://a.test,ev1.txt\n"
        "LIC1,APPROVED,YES,https://a.test,ev1.txt\n",
        encoding="utf-8",
    )
    _, led_errs = ve.load_ledger_checked(dup_led)
    assert any("DUPLICATE_LEDGER_ASSET_ID" in e for e in led_errs)

    # R2-20 & R2-21: Release EDL with VERIFIED_WITH_EVIDENCE without run_dir -> MUST FAIL!
    edl = json.loads((SKILL_DIR / "templates" / "EDL.example.json").read_text(encoding="utf-8"))
    inv = {
        "U001": {"source_id": "U001", "relative_label": "a.mp4", "media_type": "video", "rights_tag": "OWNED", "sha256": "a" * 64, "duration_s": 5.0, "width": 1080, "height": 1920, "probe_status": "OK"},
        "U002": {"source_id": "U002", "relative_label": "b.mp4", "media_type": "video", "rights_tag": "OWNED", "sha256": "b" * 64, "duration_s": 6.0, "width": 1920, "height": 1080, "probe_status": "OK"},
        "U003": {"source_id": "U003", "relative_label": "c.wav", "media_type": "audio", "rights_tag": "OWNED", "sha256": "c" * 64, "duration_s": 10.0, "width": 0, "height": 0, "probe_status": "OK"},
    }
    res_no_rundir = ve.validate_all(edl, inventory=inv, run_dir=None, validation_mode="release")
    assert res_no_rundir["status"] == "FAIL_EDL_INVALID"
    assert any("MISSING_RUN_DIR_FOR_CLAIM_EVIDENCE" in e for e in res_no_rundir["errors"])

    # R2-21: Evidence file exists, but fragment anchor #U001 is MISSING inside file -> FAIL!
    (tmp_path / "SOURCE_TRUTH.md").write_text("# Truth\nPlaceholder text with no matching ID.\n", encoding="utf-8")
    res_bad_anchor = ve.validate_all(edl, inventory=inv, run_dir=tmp_path, validation_mode="release")
    assert any("CLAIM_EVIDENCE_ANCHOR_NOT_FOUND" in e for e in res_bad_anchor["errors"])

    # Anchor present + structural pass without on-disk integrity (release_ready=False!)
    (tmp_path / "SOURCE_TRUTH.md").write_text("# Truth\n- U001: verified product shot.\n", encoding="utf-8")
    res_good = ve.validate_all(edl, inventory=inv, run_dir=tmp_path, validation_mode="release")
    assert res_good["status"] == "PASS_EDL_STRUCTURAL_ONLY", res_good["errors"]
    assert res_good["release_ready"] is False
    assert res_good["source_integrity_status"] == "SOURCE_INTEGRITY_NOT_VERIFIED_ON_DISK"

    edl_missing_claim_src = copy.deepcopy(edl)
    edl_missing_claim_src["claims"][0]["source_id"] = "U999"
    res_cs = ve.validate_all(edl_missing_claim_src, inventory=inv, run_dir=tmp_path, validation_mode="release")
    assert any("CLAIM_SOURCE_ID_NOT_IN_INVENTORY" in e for e in res_cs["errors"])

    # R2-22: Windows backslash traversal rejected even on POSIX/macOS!
    assert ve._is_safe_relative_label(r"..\..\secret.txt") is False
    assert ve._is_safe_relative_label(r"sub\..\escape.mp4") is False
    assert ve._is_safe_relative_label(r"\Windows\System32\cmd.exe") is False

    # R2-23: Source integrity gate required for C2 final check (with complete per-file SHA-256 verification)
    res_req_int = ve.validate_all(edl, inventory=inv, run_dir=tmp_path, validation_mode="release", require_source_integrity=True)
    assert res_req_int["status"] == "FAIL_EDL_INVALID"
    assert any("MISSING_SOURCE_INTEGRITY_CHECK" in e for e in res_req_int["errors"])

    complete_int_pass = {
        "checked_at": "2026-11-23T13:00:00Z",
        "status": "PASS_SOURCES_UNCHANGED",
        "entries": [
            {"source_id": "U001", "root_id": "R01", "relative_label": "a.mp4", "expected_sha256": "a" * 64, "actual_sha256": "a" * 64, "status": "UNCHANGED"},
            {"source_id": "U002", "root_id": "R01", "relative_label": "b.mp4", "expected_sha256": "b" * 64, "actual_sha256": "b" * 64, "status": "UNCHANGED"},
            {"source_id": "U003", "root_id": "R01", "relative_label": "c.wav", "expected_sha256": "c" * 64, "actual_sha256": "c" * 64, "status": "UNCHANGED"},
        ],
    }
    res_int_ok = ve.validate_all(
        edl, inventory=inv, run_dir=tmp_path, validation_mode="release",
        source_integrity_report=complete_int_pass, require_source_integrity=True,
    )
    assert res_int_ok["status"] == "PASS_EDL_VALID_FOR_RELEASE", res_int_ok["errors"]
    assert res_int_ok["source_integrity_status"] == "PASS_SOURCE_INTEGRITY"
    assert res_int_ok["release_ready"] is True


def test_r2_15_26_31_permissions_incomplete_bad_ffmpeg_and_missing_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # R2-15: Permission/scandir error marks scan_complete=False (incomplete)
    def _raise_perm(_p):
        raise PermissionError("simulated TCC denial")

    perm_dir = tmp_path / "tcc_protected"
    perm_dir.mkdir()
    monkeypatch.setattr(ps.os, "scandir", _raise_perm)
    det = ps.discover_inputs_detailed([str(perm_dir)])
    assert det["scan_complete"] is False
    assert any("SCANDIR_ERROR" in r for r in det["incomplete_reasons"])
    monkeypatch.undo()

    # R2-26: ffmpeg error during audio measurement cannot PASS
    mp4 = tmp_path / f"{FIXTURE_TAG}_bad_ff.mp4"
    _make_unit_mp4(mp4, duration_s=1.2)
    probe_ok = vx.probe_export(mp4)
    monkeypatch.setattr(
        vx.subprocess, "run",
        lambda cmd, *a, **kw: subprocess.CompletedProcess(cmd, 1, "", "simulated audio filter error"),
    )
    res_aud_err = vx.measure_audio_segments(mp4, require_audio=True, probe_data=probe_ok)
    assert res_aud_err["audio_signal_status"] == "FAIL_AUDIO_FFMPEG_ERROR"
    monkeypatch.undo()

    # R2-31: Missing Concat binary -> c0_ready_for_mcp=False & BLOCKED_ENV_CONCAT_BINARY_MISSING
    monkeypatch.setattr(pa, "discover_concat_binary", lambda *_a, **_kw: {
        "binary_status": "BINARY_BLOCKED_NOT_FOUND",
        "binary_source": "NOT_FOUND",
        "app_binary": "NOT_FOUND",
        "app_arch": "UNKNOWN",
        "app_version": "NOT_INSTALLED",
        "app_sha256": None,
    })
    monkeypatch.setattr(pa, "_disk_usage_gb", lambda _p: (40.0, 460.0))
    env = pa.probe_host_environment(system="Darwin", machine="arm64", os_version="14.4.1")
    assert env["c0_ready_for_mcp"] is False
    assert env["c0_status"] == "BLOCKED_ENV_CONCAT_BINARY_MISSING"
