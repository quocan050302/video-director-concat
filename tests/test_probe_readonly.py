"""Read-only probing, hash integrity, path-guard, Unicode, and silent-media tests (T05, T06, T12)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import probe_sources as ps  # noqa: E402
import verify_source_hashes as vsh  # noqa: E402


def _make_silent_mp4(dest: Path) -> None:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        pytest.skip("ffmpeg not installed in test environment")
    cmd = [
        ffmpeg_bin,
        "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=1.5:size=320x240:rate=30",
        "-an",
        "-pix_fmt", "yuv420p",
        "-y", str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_t05_t12_probe_readonly_unicode_and_drift_detection(tmp_path: Path) -> None:
    src_dir = tmp_path / "owned_sources"
    src_dir.mkdir()
    clip = src_dir / "cảnh quay mẫu 'test' 01.mp4"
    _make_silent_mp4(clip)

    sha_before = ps.stream_sha256(clip)
    inv_csv = tmp_path / "SOURCE_INVENTORY.csv"
    stills_dir = tmp_path / "stills"

    rc = ps.main([
        str(src_dir),
        "--out-csv", str(inv_csv),
        "--contact-dir", str(stills_dir),
        "--rights-tag", "OWNED",
        "--workers", "1",
    ])
    assert rc == 0
    assert ps.stream_sha256(clip) == sha_before

    records = vsh.load_manifest(inv_csv)
    assert len(records) == 1
    assert records[0]["has_audio"] == "False"  # T12: silent video detected without paid transcription
    assert records[0]["probe_status"] == "OK"

    unchanged = vsh.verify_unchanged(records, src_dir)
    assert unchanged["status"] == "PASS_SOURCES_UNCHANGED"

    # Simulate tampering -> verify_source_hashes MUST detect drift and never auto-fix
    clip.write_bytes(clip.read_bytes() + b"\x00")
    drifted = vsh.verify_unchanged(records, src_dir)
    assert drifted["status"] == "FAIL_SOURCE_DRIFT_OR_MISSING"
    assert len(drifted["drifted"]) == 1


def test_t06_path_traversal_symlink_and_protected_dirs_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"dummy")

    safe_dir = tmp_path / "safe"
    safe_dir.mkdir()
    escape_link = safe_dir / "escape.mp4"
    escape_link.symlink_to(outside)

    discovered, rejected = ps.discover_inputs(
        [str(safe_dir), str(safe_dir / ".." / "outside.mp4"), "/System"],
        limits={"max_files": 10},
    )
    assert discovered == []
    reasons = {r["reason"] for r in rejected}
    assert "SYMLINK_FILE_REJECTED" in reasons
    assert "PATH_TRAVERSAL_REJECTED" in reasons
    assert "PROTECTED_SYSTEM_PATH_REJECTED" in reasons
