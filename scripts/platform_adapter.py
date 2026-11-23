#!/usr/bin/env python3
"""Cross-platform environment probe and platform adapter (Windows & macOS).

Read-only by design: detects OS, CPU architecture, RAM/pressure, disk space,
FFmpeg/ffprobe availability, official Concat binary candidates, and Antigravity
global skill / MCP config locations without mutating system security settings.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

MIN_DISK_WARN_GB = 20.0
MIN_DISK_BLOCK_GB = 5.0


def _run_readonly(cmd: list[str], timeout_s: int = 10) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, "", str(exc)


def _parse_version_tuple(version_str: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", version_str or "")
    return tuple(int(n) for n in nums[:3])


def detect_platform_profile(
    system: str | None = None,
    machine: str | None = None,
    os_version: str | None = None,
    home_dir: str | None = None,
    local_app_data: str | None = None,
) -> dict[str, Any]:
    """Return canonical platform overrides for Windows x64, macOS arm64, and macOS x86_64."""
    sys_name = (system or platform.system()).strip()
    mach_raw = (machine or platform.machine()).strip().lower()

    if mach_raw in {"arm64", "aarch64"}:
        arch = "arm64"
    elif mach_raw in {"x86_64", "amd64", "x64"}:
        arch = "x86_64"
    else:
        arch = mach_raw or "unknown"

    home = Path(home_dir) if home_dir else Path.home()

    if sys_name == "Darwin":
        ver = os_version if os_version is not None else platform.mac_ver()[0]
        ver_tuple = _parse_version_tuple(ver)
        os_supported = True
        os_gate = "SUPPORTED"
        model_compat = "FULL_SUPPORTED_PER_DOCS"
        if ver_tuple and ver_tuple < (12, 0):
            os_supported = False
            os_gate = "BLOCKED_OS_VERSION"
            model_compat = "BLOCKED_OS_VERSION"
        elif arch == "x86_64" and ver_tuple and ver_tuple < (13, 4):
            model_compat = "EDITOR_OK_ONNX_REQUIRES_MACOS_13_4"

        asset_suffix = "macos-arm64.dmg" if arch == "arm64" else "macos-x86_64.dmg"
        binary_candidates = [
            "/Applications/Concat.app/Contents/MacOS/concat",
            str(home / "Applications" / "Concat.app" / "Contents" / "MacOS" / "concat"),
        ]
        return {
            "platform_id": f"macos-{arch}",
            "os_family": "macos",
            "system": "Darwin",
            "arch": arch,
            "os_version": ver or "UNKNOWN",
            "os_supported": os_supported,
            "os_gate_status": os_gate,
            "model_compatibility": model_compat,
            "override_reference": "references/platform_macos.md",
            "roots_separator": ":",
            "official_asset_pattern": f"Concat-<version>-{asset_suffix}",
            "concat_binary_candidates": binary_candidates,
            "mcp_args_deterministic": ["--mcp", "headless"],
            "global_skill_dir": str(home / ".gemini" / "config" / "skills" / "video-director-concat"),
            "mcp_config_candidates": [
                str(home / ".gemini" / "config" / "mcp_config.json"),
                str(home / ".gemini" / "antigravity" / "mcp_config.json"),
            ],
            "recommended_workspace_roots": [
                str(home / "Movies" / "AntigravityConcat"),
                str(home / "Projects" / "AntigravityConcat"),
            ],
            "security_gate_type": "GATEKEEPER_QUARANTINE_AND_TCC",
            "forbidden_security_bypasses": [
                "spctl --master-disable",
                "csrutil disable",
                "tccutil",
                "auto xattr -dr com.apple.quarantine without owner approval",
            ],
            "memory_model": "UNIFIED_MEMORY_PRESSURE" if arch == "arm64" else "SYSTEM_RAM_AND_PRESSURE",
        }

    if sys_name == "Windows":
        ver = os_version if os_version is not None else platform.version()
        localappdata = local_app_data or os.environ.get("LOCALAPPDATA", r"C:\Users\<local-user>\AppData\Local")
        binary_candidates = [
            r"C:\Program Files\Concat\concat.exe",
            str(Path(localappdata) / "Programs" / "Concat" / "concat.exe"),
        ]
        return {
            "platform_id": f"windows-{arch}",
            "os_family": "windows",
            "system": "Windows",
            "arch": arch,
            "os_version": ver or "UNKNOWN",
            "os_supported": arch == "x86_64",
            "os_gate_status": "SUPPORTED" if arch == "x86_64" else "UNSUPPORTED_CURRENT_VERSION",
            "model_compatibility": "CHECK_HOST_RAM_AND_GPU",
            "override_reference": "references/platform_windows.md",
            "roots_separator": ";",
            "official_asset_pattern": "Concat-<version>-windows-x86_64-setup.exe",
            "concat_binary_candidates": binary_candidates,
            "mcp_args_deterministic": ["--mcp", "headless"],
            "global_skill_dir": str(home / ".gemini" / "config" / "skills" / "video-director-concat"),
            "mcp_config_candidates": [
                str(home / ".gemini" / "config" / "mcp_config.json"),
            ],
            "recommended_workspace_roots": [
                str(home / "Videos" / "AntigravityConcat"),
            ],
            "security_gate_type": "SMARTSCREEN_AND_UAC",
            "forbidden_security_bypasses": [
                "disable Windows Defender",
                "disable SmartScreen",
                "bypass UAC",
                "irm | iex untrusted script",
            ],
            "memory_model": "SYSTEM_RAM_AND_GPU_VRAM",
        }

    return {
        "platform_id": f"{sys_name.lower()}-{arch}",
        "os_family": sys_name.lower(),
        "system": sys_name,
        "arch": arch,
        "os_version": os_version or platform.release(),
        "os_supported": False,
        "os_gate_status": "UNSUPPORTED_BY_THIS_ADAPTER",
        "model_compatibility": "UNKNOWN",
        "override_reference": "README_INSTALL.md",
        "roots_separator": ":",
        "official_asset_pattern": "SEE_OFFICIAL_GITHUB_RELEASES",
        "concat_binary_candidates": ["/usr/bin/concat"],
        "mcp_args_deterministic": ["--mcp", "headless"],
        "global_skill_dir": str(home / ".gemini" / "config" / "skills" / "video-director-concat"),
        "mcp_config_candidates": [
            str(home / ".gemini" / "config" / "mcp_config.json"),
        ],
        "recommended_workspace_roots": [str(home / "AntigravityConcat")],
        "security_gate_type": "STANDARD_PACKAGE_VERIFICATION",
        "forbidden_security_bypasses": ["curl | bash"],
        "memory_model": "SYSTEM_RAM",
    }


def format_concat_mcp_roots(paths: list[str], system: str | None = None) -> str:
    """Join allowlisted roots using OS-native separator (':' on macOS/POSIX, ';' on Windows)."""
    profile = detect_platform_profile(system=system)
    sep = profile["roots_separator"]
    cleaned = [p.strip() for p in paths if p and p.strip()]
    return sep.join(cleaned)


def _probe_macos_hardware() -> dict[str, Any]:
    info: dict[str, Any] = {
        "os_version": "UNKNOWN",
        "cpu_cores": os.cpu_count() or 0,
        "ram_total_bytes": None,
        "ram_available_or_unknown": "UNKNOWN",
        "gpu_model_or_unknown": "UNKNOWN",
        "metal_capability_or_unknown": "UNKNOWN",
    }
    rc, out, _ = _run_readonly(["sw_vers", "-productVersion"])
    if rc == 0 and out:
        info["os_version"] = out

    rc, out, _ = _run_readonly(["sysctl", "-n", "hw.logicalcpu"])
    if rc == 0 and out.isdigit():
        info["cpu_cores"] = int(out)

    rc, out, _ = _run_readonly(["sysctl", "-n", "hw.memsize"])
    if rc == 0 and out.isdigit():
        info["ram_total_bytes"] = int(out)

    rc, out, _ = _run_readonly(["vm_stat"])
    if rc == 0 and out:
        page_match = re.search(r"page size of (\d+) bytes", out)
        page_size = int(page_match.group(1)) if page_match else 16384
        pages: dict[str, int] = {}
        for line in out.splitlines():
            m = re.match(r"Pages\s+([^:]+):\s+(\d+)\.", line.strip())
            if m:
                pages[m.group(1).strip().lower()] = int(m.group(2))
        free_like = (
            pages.get("free", 0)
            + pages.get("inactive", 0)
            + pages.get("speculative", 0)
            + pages.get("purgeable", 0)
        )
        if free_like > 0:
            avail_gb = round((free_like * page_size) / (1024**3), 2)
            info["ram_available_or_unknown"] = f"{avail_gb} GiB (free+inactive+speculative+purgeable estimate)"

    rc, out, _ = _run_readonly(["system_profiler", "SPDisplaysDataType"], timeout_s=12)
    if rc == 0 and out:
        m_gpu = re.search(r"Chipset Model:\s*(.+)", out)
        m_metal = re.search(r"Metal Support:\s*(.+)", out)
        if m_gpu:
            info["gpu_model_or_unknown"] = m_gpu.group(1).strip()
        if m_metal:
            info["metal_capability_or_unknown"] = m_metal.group(1).strip()

    return info


def _probe_binary_version(binary_name: str, version_args: list[str] | None = None) -> dict[str, Any]:
    resolved = shutil.which(binary_name)
    if not resolved:
        return {"found": False, "path": None, "version": "MISSING"}
    args = [resolved] + (version_args or ["--version"])
    rc, out, err = _run_readonly(args, timeout_s=8)
    first_line = (out or err).splitlines()[0] if (out or err) else "UNKNOWN"
    return {"found": True, "path": resolved, "version": first_line, "exit_code": rc}


def probe_host_environment() -> dict[str, Any]:
    """Execute bounded read-only M0/C0 probe on the current host."""
    sys_name = platform.system()
    mac_hw = _probe_macos_hardware() if sys_name == "Darwin" else None
    os_ver = mac_hw["os_version"] if mac_hw else platform.version()
    profile = detect_platform_profile(system=sys_name, machine=platform.machine(), os_version=os_ver)

    disk = shutil.disk_usage(Path.home())
    disk_free_gb = round(disk.free / (1024**3), 2)
    disk_total_gb = round(disk.total / (1024**3), 2)
    if disk_free_gb < MIN_DISK_BLOCK_GB:
        disk_status = "BLOCKED_LOW_DISK"
    elif disk_free_gb < MIN_DISK_WARN_GB:
        disk_status = "WARN_LOW_DISK"
    else:
        disk_status = "OK"

    found_concat: str | None = None
    for cand in profile["concat_binary_candidates"]:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            found_concat = cand
            break

    concat_arch = "UNKNOWN"
    concat_version = "NOT_INSTALLED"
    if found_concat and sys_name == "Darwin":
        rc, out, _ = _run_readonly(["file", found_concat], timeout_s=5)
        if rc == 0 and out:
            concat_arch = "arm64" if "arm64" in out else ("x86_64" if "x86_64" in out else out)

    discovered_mcp_configs = []
    for cfg in profile["mcp_config_candidates"]:
        p = Path(cfg)
        if p.exists() or p.is_symlink():
            discovered_mcp_configs.append(
                {
                    "path": str(p),
                    "exists": p.exists(),
                    "is_symlink": p.is_symlink(),
                    "size_bytes": p.stat().st_size if p.exists() else 0,
                }
            )

    ffprobe_info = _probe_binary_version("ffprobe", ["-version"])
    ffmpeg_info = _probe_binary_version("ffmpeg", ["-version"])
    shasum_info = _probe_binary_version("shasum", ["--version"]) if sys_name == "Darwin" else None

    ram_total_bytes = mac_hw["ram_total_bytes"] if mac_hw else None
    ram_total_str = f"{round(ram_total_bytes / (1024**3), 2)} GiB" if ram_total_bytes else "UNKNOWN"

    env_matrix = {
        "time_checked": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform_profile": profile,
        "os_version": profile["os_version"],
        "arch": profile["arch"],
        "cpu_cores": mac_hw["cpu_cores"] if mac_hw else (os.cpu_count() or 0),
        "ram_total": ram_total_str,
        "ram_available_or_unknown": mac_hw["ram_available_or_unknown"] if mac_hw else "UNKNOWN",
        "gpu_model_or_unknown": mac_hw["gpu_model_or_unknown"] if mac_hw else "UNKNOWN",
        "metal_capability_or_unknown": mac_hw["metal_capability_or_unknown"] if mac_hw else "UNKNOWN",
        "disk_free": f"{disk_free_gb} GiB / {disk_total_gb} GiB",
        "disk_free_gb": disk_free_gb,
        "disk_safety_status": disk_status,
        "app_binary": found_concat or "NOT_FOUND",
        "app_arch": concat_arch,
        "app_version": concat_version,
        "model_compatibility": profile["model_compatibility"],
        "ffprobe_version_or_missing": ffprobe_info["version"],
        "ffmpeg_version_or_missing": ffmpeg_info["version"],
        "shasum_available": bool(shasum_info and shasum_info["found"]) if shasum_info else "N/A",
        "python_version": platform.python_version(),
        "mcp_client_runtime": discovered_mcp_configs,
        "c0_ready_for_mcp": bool(profile["os_supported"] and found_concat and ffprobe_info["found"]),
        "c0_status": (
            "ENV_VERIFIED_READY_FOR_MCP"
            if (profile["os_supported"] and found_concat and ffprobe_info["found"])
            else (
                "BLOCKED_OS_VERSION"
                if not profile["os_supported"]
                else ("BLOCKED_ENV_CONCAT_NOT_INSTALLED" if not found_concat else "BLOCKED_ENV_FFPROBE_MISSING")
            )
        ),
    }
    return env_matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only cross-platform environment adapter for video-director-concat.")
    parser.add_argument("--json", action="store_true", help="Print full ENV_MATRIX JSON to stdout.")
    parser.add_argument("--out", type=Path, help="Optional path to write ENV_MATRIX JSON.")
    args = parser.parse_args(argv)

    result = probe_host_environment()
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    if args.json or not args.out:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
