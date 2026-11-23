"""Cross-platform auto-detection and macOS override tests."""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import platform_adapter as pa  # noqa: E402


def test_macos_arm64_overrides_applied() -> None:
    prof = pa.detect_platform_profile(
        system="Darwin",
        machine="arm64",
        os_version="14.4.1",
        home_dir="/Users/<local-user>",
    )
    assert prof["platform_id"] == "macos-arm64"
    assert prof["os_supported"] is True
    assert prof["roots_separator"] == ":"
    assert prof["override_reference"] == "references/platform_macos.md"
    assert prof["official_asset_pattern"] == "Concat-<version>-macos-arm64.dmg"
    assert "/Applications/Concat.app/Contents/MacOS/concat" in prof["concat_binary_candidates"]
    assert prof["mcp_args_deterministic"] == ["--mcp", "headless"]
    assert prof["memory_model"] == "UNIFIED_MEMORY_PRESSURE"
    assert prof["security_gate_type"] == "GATEKEEPER_QUARANTINE_AND_TCC"


def test_macos_intel_12_onnx_caveat_and_unsupported_macos_11() -> None:
    prof_12 = pa.detect_platform_profile(
        system="Darwin",
        machine="x86_64",
        os_version="12.7.4",
        home_dir="/Users/<local-user>",
    )
    assert prof_12["os_supported"] is True
    assert prof_12["official_asset_pattern"] == "Concat-<version>-macos-x86_64.dmg"
    assert prof_12["model_compatibility"] == "EDITOR_OK_ONNX_REQUIRES_MACOS_13_4"

    prof_11 = pa.detect_platform_profile(
        system="Darwin",
        machine="x86_64",
        os_version="11.7.10",
        home_dir="/Users/<local-user>",
    )
    assert prof_11["os_supported"] is False
    assert prof_11["os_gate_status"] == "BLOCKED_OS_VERSION"


def test_windows_x64_profile_and_roots_separator() -> None:
    prof = pa.detect_platform_profile(
        system="Windows",
        machine="AMD64",
        os_version="10.0.22631",
        home_dir=r"C:\Users\<local-user>",
        local_app_data=r"C:\Users\<local-user>\AppData\Local",
    )
    assert prof["platform_id"] == "windows-x86_64"
    assert prof["os_supported"] is True
    assert prof["roots_separator"] == ";"
    assert prof["override_reference"] == "references/platform_windows.md"
    assert r"C:\Program Files\Concat\concat.exe" in prof["concat_binary_candidates"]
    assert prof["security_gate_type"] == "SMARTSCREEN_AND_UAC"


def test_format_concat_mcp_roots_by_os() -> None:
    mac_roots = pa.format_concat_mcp_roots(["/Volumes/SSD/Clips", "/Users/<local-user>/Movies/AntigravityConcat"], system="Darwin")
    assert mac_roots == "/Volumes/SSD/Clips:/Users/<local-user>/Movies/AntigravityConcat"

    win_roots = pa.format_concat_mcp_roots([r"D:\Clips", r"D:\Runs"], system="Windows")
    assert win_roots == r"D:\Clips;D:\Runs"
