"""Negative tests proving QA never fabricates PASS (T09 and fail-closed export gates)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import validate_edl as ve  # noqa: E402
import verify_export as vx  # noqa: E402


def _ffmpeg_or_skip() -> str:
    b = shutil.which("ffmpeg")
    if not b:
        pytest.skip("ffmpeg not installed in test environment")
    return b


def test_nonexistent_empty_tmp_and_corrupt_mp4_fail_closed(tmp_path: Path) -> None:
    r_missing = vx.evaluate_export(tmp_path / "does_not_exist.mp4", qa_level="technical")
    assert r_missing["mp4_qa_pass"] is False
    assert r_missing["probe"]["status"] == "FAIL_EXPORT_MISSING"

    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    r_empty = vx.evaluate_export(empty, qa_level="technical")
    assert r_empty["mp4_qa_pass"] is False
    assert r_empty["probe"]["status"] == "FAIL_EXPORT_EMPTY"

    partial = tmp_path / "export.mp4.tmp"
    partial.write_bytes(b"partial")
    r_tmp = vx.evaluate_export(partial, qa_level="technical")
    assert r_tmp["mp4_qa_pass"] is False
    assert r_tmp["probe"]["status"] == "FAIL_NOT_FINAL_MP4"

    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"NOT_A_VALID_MP4_CONTAINER_HEADER_1234567890")
    r_corrupt = vx.evaluate_export(corrupt, qa_level="technical")
    assert r_corrupt["mp4_qa_pass"] is False
    assert r_corrupt["probe"]["status"] == "FAIL_EXPORT_DECODE"


def test_real_mp4_never_fakes_perceptual_audio_and_detects_missing_audio(tmp_path: Path) -> None:
    ffmpeg_bin = _ffmpeg_or_skip()
    silent_mp4 = tmp_path / "silent.mp4"
    subprocess.run(
        [
            ffmpeg_bin, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=duration=2.0:size=320x240:rate=30",
            "-an", "-pix_fmt", "yuv420p", "-y", str(silent_mp4),
        ],
        check=True,
    )
    r_silent = vx.evaluate_export(silent_mp4, require_audio=True, qa_level="technical")
    assert r_silent["mp4_qa_pass"] is False
    assert r_silent["audio_signal_status"] == "FAIL_NO_AUDIO_STREAM"

    av_mp4 = tmp_path / "clean_av.mp4"
    subprocess.run(
        [
            ffmpeg_bin, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=duration=2.0:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
            "-af", "volume=-14dB",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y", str(av_mp4),
        ],
        check=True,
    )
    r_av = vx.evaluate_export(av_mp4, require_audio=True, perceptual_audio_evidence=None, qa_level="technical")
    assert r_av["mp4_qa_pass"] is True
    assert r_av["release_gate_pass"] is False
    assert r_av["audio_signal_status"] == "PASS_AUDIO_SIGNAL"
    assert r_av["audio_perceptual_status"] == "PERCEPTUAL_AUDIO_PENDING"
    assert r_av["overall_status"] == "PASS_TECHNICAL_ONLY"
    assert r_av["audio_check"]["integrated_lufs"] is not None


def test_unintended_black_fails_while_edl_intentional_black_allowed(tmp_path: Path) -> None:
    ffmpeg_bin = _ffmpeg_or_skip()
    black_mp4 = tmp_path / "black.mp4"
    subprocess.run(
        [
            ffmpeg_bin, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1.2:r=30",
            "-an", "-pix_fmt", "yuv420p", "-y", str(black_mp4),
        ],
        check=True,
    )
    r_unplanned = vx.detect_unintended_blacks_and_freezes(black_mp4, edl=None)
    assert r_unplanned["status"] == "FAIL_UNINTENDED_BLACK_OR_FREEZE"
    assert len(r_unplanned["unintended_blacks"]) >= 1

    edl_planned = {
        "output_spec": {"timeline_fps": "30/1"},
        "shots": [
            {
                "shot_id": "S001",
                "output_in_frame": 0,
                "output_out_frame": 36,
                "intentional_black": True,
                "intentional_freeze": True,
            }
        ],
    }
    r_planned = vx.detect_unintended_blacks_and_freezes(black_mp4, edl=edl_planned)
    assert r_planned["status"] == "PASS"
    assert len(r_planned["intentional_blacks"]) >= 1


def test_empty_project_and_missing_mcp_gates_cannot_pass() -> None:
    empty_edl = {"output_spec": {"width": 1080, "height": 1920, "timeline_fps": "30/1"}, "shots": []}
    res = ve.validate_all(empty_edl, inventory={}, validation_mode="release")
    assert res["status"] == "FAIL_EDL_INVALID"
    assert any("EMPTY_SHOT_LIST" in e for e in res["errors"])

    assert vx.main(["--mp4", "/nonexistent/fake_export.mp4", "--qa-level", "release"]) == 1
