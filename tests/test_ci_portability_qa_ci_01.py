"""QA-CI-01 Cross-Platform macOS / Linux / Windows Portability & Regression Suite.

Covers the 4 Ubuntu CI portability failures from GitHub Actions run 45186149291:
1. Cross-OS protected system path enforcement in probe_sources.py (macOS, Linux, Windows)
   prior to exists()/is_symlink() so non-existent or symlinked system dirs fail closed as
   PROTECTED_SYSTEM_PATH_REJECTED.
2. Fail-closed Linux production gate in platform_adapter.py (never treats Linux as macOS or
   supported production OS, even with ample disk and an executable present).
3. Deterministic macOS/Windows/Linux host probe evaluation independent of the CI runner OS.
4. Bounded parallel deterministic probing across worker counts (workers=1, 2, 4).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import platform_adapter as pa  # noqa: E402
import probe_sources as ps  # noqa: E402


def _ffmpeg_or_skip() -> str:
    b = shutil.which("ffmpeg")
    if not b:
        pytest.skip("ffmpeg not installed")
    return b


def _make_tiny_mp4(dest: Path, duration_s: float = 1.0) -> None:
    cmd = [
        _ffmpeg_or_skip(), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=duration={duration_s}:size=160x120:rate=30",
        "-an", "-pix_fmt", "yuv420p", "-y", str(dest),
    ]
    subprocess.run(cmd, check=True)


def test_qa_ci_01_protected_system_paths_cross_os_macos_linux_windows(tmp_path: Path) -> None:
    """Protected macOS, Linux, and Windows system paths reject as PROTECTED_SYSTEM_PATH_REJECTED on every OS."""
    candidates = [
        "/",
        "/System",
        "/System/Library",
        "/Library",
        "/Users",
        "/home",
        "/root",
        "/etc",
        "/etc/passwd",
        "/bin",
        "/sbin",
        "/proc",
        "/proc/self",
        "/sys",
        "/dev",
        "/boot",
        str(Path.home()),
        r"C:\Windows",
        r"C:\Windows\System32",
        r"C:\Users",
    ]
    det = ps.discover_inputs_detailed(candidates, limits={"max_files": 20})
    assert det["discovered"] == []
    assert det["scan_complete"] is False
    by_path = {r["path"]: r["reason"] for r in det["rejected"]}
    for c in candidates:
        assert by_path.get(c) == "PROTECTED_SYSTEM_PATH_REJECTED", f"Expected protected rejection for {c!r}, got {by_path.get(c)!r}"

    # Normal workspace directory under tmp_path MUST still be allowed (no over-blocking)
    allowed_dir = tmp_path / "clips"
    allowed_dir.mkdir()
    clip = allowed_dir / "ok.mp4"
    clip.write_bytes(b"0123")
    det_ok = ps.discover_inputs_detailed([str(allowed_dir)])
    assert det_ok["scan_complete"] is True
    assert len(det_ok["discovered"]) == 1

    # Non-protected top-level symlink MUST still reject as TOP_LEVEL_SYMLINK_REJECTED
    sym_dir = tmp_path / "sym_clips"
    sym_dir.symlink_to(allowed_dir)
    det_sym = ps.discover_inputs_detailed([str(sym_dir)])
    assert det_sym["discovered"] == []
    assert det_sym["rejected"][0]["reason"] == "TOP_LEVEL_SYMLINK_REJECTED"


def test_qa_ci_01_linux_production_gate_remains_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Linux must NEVER be treated as a supported production Concat OS even with binary + ample disk."""
    fake_bin = {
        "binary_status": "BINARY_FOUND",
        "binary_source": "PATH",
        "app_binary": "/usr/bin/concat",
        "app_arch": "x86_64",
        "app_version": "0.2.12",
        "app_sha256": "a" * 64,
    }
    monkeypatch.setattr(pa, "discover_concat_binary", lambda *_a, **_kw: fake_bin)
    monkeypatch.setattr(pa, "_disk_usage_gb", lambda _p: (120.0, 500.0))

    env_linux = pa.probe_host_environment(system="Linux", machine="x86_64", os_version="6.8.0-ubuntu")
    assert env_linux["platform_profile"]["os_supported"] is False
    assert env_linux["env_supported_status"] == "UNSUPPORTED_BY_THIS_ADAPTER"
    assert env_linux["c0_ready_for_mcp"] is False
    assert env_linux["c0_status"] == "BLOCKED_UNSUPPORTED_OS"

    # Verify read-only /proc/meminfo parser safely extracts Linux RAM when present
    fake_meminfo = tmp_path / "meminfo"
    fake_meminfo.write_text("MemTotal:       16384000 kB\nMemAvailable:    8192000 kB\n", encoding="utf-8")
    hw = pa._probe_linux_hardware(meminfo_path=fake_meminfo)
    assert hw["ram_total_bytes"] == 16384000 * 1024
    assert "GiB" in hw["ram_available_or_unknown"]


def test_qa_ci_01_macos_and_windows_gates_deterministic_from_any_ci_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supported-OS C0 gates (macOS arm64, macOS 11 blocked, Windows x64) evaluate identically on Linux or macOS."""
    found_bin = {
        "binary_status": "BINARY_FOUND",
        "binary_source": "OFFICIAL_APP_BUNDLE",
        "app_binary": "/Applications/Concat.app/Contents/MacOS/concat",
        "app_arch": "arm64",
        "app_version": "0.2.12",
        "app_sha256": "b" * 64,
    }
    missing_bin = {
        "binary_status": "BINARY_BLOCKED_NOT_FOUND",
        "binary_source": "NOT_FOUND",
        "app_binary": "NOT_FOUND",
        "app_arch": "UNKNOWN",
        "app_version": "NOT_INSTALLED",
        "app_sha256": None,
    }

    # Simulate running on an Ubuntu Linux runner underneath
    monkeypatch.setattr(pa.platform, "system", lambda: "Linux")
    monkeypatch.setattr(pa.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(pa, "_disk_usage_gb", lambda _p: (40.0, 460.0))

    # macOS 14.4.1 + binary -> C0 ready
    monkeypatch.setattr(pa, "discover_concat_binary", lambda *_a, **_kw: found_bin)
    mac_ok = pa.probe_host_environment(system="Darwin", machine="arm64", os_version="14.4.1")
    assert mac_ok["c0_ready_for_mcp"] is True
    assert mac_ok["c0_status"] == "C0_READY_FOR_MCP_HANDSHAKE"

    # macOS 11.7 -> BLOCKED_OS_VERSION even with binary
    mac_old = pa.probe_host_environment(system="Darwin", machine="x86_64", os_version="11.7.10")
    assert mac_old["c0_ready_for_mcp"] is False
    assert mac_old["c0_status"] == "BLOCKED_OS_VERSION"

    # Windows x64 + missing binary -> BLOCKED_ENV_CONCAT_BINARY_MISSING
    monkeypatch.setattr(pa, "discover_concat_binary", lambda *_a, **_kw: missing_bin)
    win_nobin = pa.probe_host_environment(system="Windows", machine="AMD64", os_version="10.0.22631")
    assert win_nobin["platform_profile"]["os_supported"] is True
    assert win_nobin["c0_ready_for_mcp"] is False
    assert win_nobin["c0_status"] == "BLOCKED_ENV_CONCAT_BINARY_MISSING"

    # Windows x64 + low disk -> BLOCKED_LOW_DISK
    monkeypatch.setattr(pa, "_disk_usage_gb", lambda _p: (2.0, 460.0))
    monkeypatch.setattr(pa, "discover_concat_binary", lambda *_a, **_kw: found_bin)
    win_low = pa.probe_host_environment(system="Windows", machine="AMD64", os_version="10.0.22631")
    assert win_low["c0_ready_for_mcp"] is False
    assert win_low["c0_status"] == "BLOCKED_LOW_DISK"


def test_qa_ci_01_bounded_parallel_probing_deterministic(tmp_path: Path) -> None:
    """Bounded parallel probing (workers=1 vs 2 vs 4) yields byte-identical CSV & JSON inventories."""
    media_dir = tmp_path / "batch"
    media_dir.mkdir()
    for idx in range(6):
        _make_tiny_mp4(media_dir / f"clip_{idx:02d}.mp4", duration_s=0.6 + 0.1 * idx)

    outputs: dict[int, tuple[str, list[dict]]] = {}
    for w in (1, 2, 4):
        csv_p = tmp_path / f"inv_w{w}.csv"
        json_p = tmp_path / f"inv_w{w}.json"
        rc = ps.main([
            str(media_dir),
            "--out-csv", str(csv_p),
            "--out-json", str(json_p),
            "--rights-tag", "OWNED",
            "--workers", str(w),
        ])
        assert rc == 0
        outputs[w] = (csv_p.read_text(encoding="utf-8"), json.loads(json_p.read_text(encoding="utf-8")))

    assert outputs[1][0] == outputs[2][0] == outputs[4][0]
    assert outputs[1][1] == outputs[2][1] == outputs[4][1]
    assert len(outputs[1][1]) == 6
    assert [r["source_id"] for r in outputs[1][1]] == ["U001", "U002", "U003", "U004", "U005", "U006"]
