#!/usr/bin/env python3
"""Cross-platform environment probe and platform adapter (Windows & macOS).

Read-only by design: detects OS, CPU architecture, RAM/pressure, disk safety,
official or source-built Concat binaries, FFmpeg/ffprobe availability, and
Antigravity skill / MCP config locations without mutating system security settings.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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


def _disk_usage_gb(path: Path) -> tuple[float, float]:
    disk = shutil.disk_usage(path)
    return round(disk.free / (1024**3), 2), round(disk.total / (1024**3), 2)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
        os_gate = "ENV_SUPPORTED"
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
            "os_gate_status": "ENV_SUPPORTED" if arch == "x86_64" else "UNSUPPORTED_CURRENT_VERSION",
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
    profile = detect_platform_profile(system=system)
    sep = profile["roots_separator"]
    cleaned = [p.strip() for p in paths if p and p.strip()]
    return sep.join(cleaned)


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def discover_concat_binary(
    profile: dict[str, Any],
    explicit_binary: str | Path | None = None,
    env: dict[str, str] | None = None,
    source_checkouts: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Discover existing Concat binary across explicit path/env, official bundle, PATH, or local Cargo source build."""
    environ = env if env is not None else os.environ
    is_win = profile.get("os_family") == "windows"
    exe_name = "concat.exe" if is_win else "concat"

    candidates: list[tuple[str, Path]] = []

    # 1. Explicit argument or CONCAT_BINARY env
    raw_explicit = str(explicit_binary) if explicit_binary else environ.get("CONCAT_BINARY", "").strip()
    if raw_explicit:
        candidates.append(("EXPLICIT_ENV_OR_ARG", Path(raw_explicit).expanduser()))

    # 2. Official installed app locations
    for cand in profile.get("concat_binary_candidates", []):
        candidates.append(("OFFICIAL_APP_BUNDLE", Path(cand)))

    # 3. PATH lookup
    on_path = shutil.which(exe_name)
    if on_path:
        candidates.append(("PATH", Path(on_path)))

    # 4. Explicitly supplied local source checkouts (Cargo release then debug)
    for checkout in source_checkouts or []:
        root = Path(checkout).expanduser()
        for label, rel in (
            ("SOURCE_BUILD_RELEASE", Path("src") / "target" / "release" / exe_name),
            ("SOURCE_BUILD_RELEASE", Path("target") / "release" / exe_name),
            ("SOURCE_BUILD_DEBUG", Path("src") / "target" / "debug" / exe_name),
            ("SOURCE_BUILD_DEBUG", Path("target") / "debug" / exe_name),
        ):
            candidates.append((label, root / rel))

    found_source = "NOT_FOUND"
    found_path: Path | None = None
    for source_kind, cand_path in candidates:
        try:
            if _is_executable_file(cand_path):
                found_source = source_kind
                found_path = cand_path.resolve()
                break
        except OSError:
            continue

    if found_path is None:
        return {
            "binary_status": "BINARY_BLOCKED_NOT_FOUND",
            "binary_source": "NOT_FOUND",
            "app_binary": "NOT_FOUND",
            "app_arch": "UNKNOWN",
            "app_version": "NOT_INSTALLED",
            "app_sha256": None,
        }

    app_arch = "UNKNOWN"
    if profile.get("os_family") == "macos":
        rc, out, _ = _run_readonly(["file", str(found_path)], timeout_s=5)
        if rc == 0 and out:
            app_arch = "arm64" if "arm64" in out else ("x86_64" if "x86_64" in out else out[:80])

    # Safe bounded version probe; never set NOT_INSTALLED when binary exists!
    rc, out, err = _run_readonly([str(found_path), "--version"], timeout_s=6)
    first_line = (out or err).splitlines()[0].strip() if (out or err) else ""
    if rc == 0 and first_line:
        app_version = first_line[:120]
    else:
        app_version = "VERSION_PENDING_MCP"

    return {
        "binary_status": "BINARY_FOUND",
        "binary_source": found_source,
        "app_binary": str(found_path),
        "app_arch": app_arch,
        "app_version": app_version,
        "app_sha256": _file_sha256(found_path),
    }


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


def _probe_linux_hardware(meminfo_path: Path = Path("/proc/meminfo")) -> dict[str, Any]:
    info: dict[str, Any] = {
        "cpu_cores": os.cpu_count() or 0,
        "ram_total_bytes": None,
        "ram_available_or_unknown": "UNKNOWN",
    }
    try:
        if meminfo_path.is_file():
            text = meminfo_path.read_text(encoding="utf-8", errors="replace")
            tot_m = re.search(r"^MemTotal:\s+(\d+)\s+kB", text, flags=re.M)
            avail_m = re.search(r"^MemAvailable:\s+(\d+)\s+kB", text, flags=re.M)
            if tot_m:
                info["ram_total_bytes"] = int(tot_m.group(1)) * 1024
            if avail_m:
                avail_gb = round((int(avail_m.group(1)) * 1024) / (1024**3), 2)
                info["ram_available_or_unknown"] = f"{avail_gb} GiB (/proc/meminfo MemAvailable)"
    except OSError:
        pass
    return info


def probe_host_environment(
    explicit_binary: str | Path | None = None,
    source_checkouts: list[str | Path] | None = None,
    *,
    system: str | None = None,
    machine: str | None = None,
    os_version: str | None = None,
) -> dict[str, Any]:
    """Execute bounded read-only M0/C0 probe with decoupled OS, disk, binary, QA-tool, and MCP statuses."""
    live_sys = platform.system()
    sys_name = (system or live_sys).strip()
    mach_name = (machine or platform.machine()).strip()

    mac_hw = _probe_macos_hardware() if (sys_name == "Darwin" and sys.platform == "darwin") else None
    linux_hw = _probe_linux_hardware() if (sys_name == "Linux" and sys.platform.startswith("linux")) else None

    if os_version is not None:
        os_ver = os_version
    elif mac_hw and mac_hw["os_version"] != "UNKNOWN":
        os_ver = mac_hw["os_version"]
    elif sys_name == "Darwin":
        os_ver = platform.mac_ver()[0] or "UNKNOWN"
    elif sys_name == "Linux":
        os_ver = platform.release()
    else:
        os_ver = platform.version()

    profile = detect_platform_profile(system=sys_name, machine=mach_name, os_version=os_ver)

    disk_free_gb, disk_total_gb = _disk_usage_gb(Path.home())
    if disk_free_gb < MIN_DISK_BLOCK_GB:
        disk_status = "DISK_BLOCK"
    elif disk_free_gb < MIN_DISK_WARN_GB:
        disk_status = "DISK_WARN"
    else:
        disk_status = "DISK_OK"

    bin_info = discover_concat_binary(
        profile,
        explicit_binary=explicit_binary,
        source_checkouts=source_checkouts,
    )

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

    qa_media_status = (
        "QA_TOOLS_READY"
        if (ffprobe_info["found"] and ffmpeg_info["found"])
        else ("QA_TOOLS_FFPROBE_MISSING" if not ffprobe_info["found"] else "QA_TOOLS_FFMPEG_MISSING")
    )

    c0_ready = bool(
        profile["os_supported"]
        and bin_info["binary_status"] == "BINARY_FOUND"
        and disk_status != "DISK_BLOCK"
    )

    if not profile["os_supported"]:
        c0_status = (
            "BLOCKED_OS_VERSION"
            if profile["os_gate_status"] == "BLOCKED_OS_VERSION"
            else "BLOCKED_UNSUPPORTED_OS"
        )
    elif disk_status == "DISK_BLOCK":
        c0_status = "BLOCKED_LOW_DISK"
    elif bin_info["binary_status"] != "BINARY_FOUND":
        c0_status = "BLOCKED_ENV_CONCAT_BINARY_MISSING"
    else:
        c0_status = "C0_READY_FOR_MCP_HANDSHAKE"

    ram_total_bytes = mac_hw["ram_total_bytes"] if mac_hw else (linux_hw["ram_total_bytes"] if linux_hw else None)
    ram_total_str = f"{round(ram_total_bytes / (1024**3), 2)} GiB" if ram_total_bytes else "UNKNOWN"
    ram_avail_str = (
        mac_hw["ram_available_or_unknown"]
        if mac_hw
        else (linux_hw["ram_available_or_unknown"] if linux_hw else "UNKNOWN")
    )
    cpu_cores = mac_hw["cpu_cores"] if mac_hw else (linux_hw["cpu_cores"] if linux_hw else (os.cpu_count() or 0))

    return {
        "time_checked": dt.datetime.now(dt.timezone.utc).isoformat(),
        "m0_status": "M0_ENV_PROBED",
        "env_supported_status": profile["os_gate_status"],
        "platform_profile": profile,
        "os_version": profile["os_version"],
        "arch": profile["arch"],
        "cpu_cores": cpu_cores,
        "ram_total": ram_total_str,
        "ram_available_or_unknown": ram_avail_str,
        "gpu_model_or_unknown": mac_hw["gpu_model_or_unknown"] if mac_hw else "UNKNOWN",
        "metal_capability_or_unknown": mac_hw["metal_capability_or_unknown"] if mac_hw else "UNKNOWN",
        "disk_free": f"{disk_free_gb} GiB / {disk_total_gb} GiB",
        "disk_free_gb": disk_free_gb,
        "disk_safety_status": disk_status,
        "binary_status": bin_info["binary_status"],
        "binary_source": bin_info["binary_source"],
        "app_binary": bin_info["app_binary"],
        "app_arch": bin_info["app_arch"],
        "app_version": bin_info["app_version"],
        "app_sha256": bin_info["app_sha256"],
        "model_compatibility": profile["model_compatibility"],
        "qa_media_tools_status": qa_media_status,
        "ffprobe_version_or_missing": ffprobe_info["version"],
        "ffmpeg_version_or_missing": ffmpeg_info["version"],
        "shasum_available": bool(shasum_info and shasum_info["found"]) if shasum_info else "N/A",
        "python_version": platform.python_version(),
        "mcp_client_runtime": discovered_mcp_configs,
        "mcp_handshake_status": "MCP_HANDSHAKE_PENDING",
        "c0_ready_for_mcp": c0_ready,
        "c0_status": c0_status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only cross-platform environment adapter for video-director-concat.")
    parser.add_argument("--json", action="store_true", help="Print full ENV_MATRIX JSON to stdout.")
    parser.add_argument("--concat-binary", type=Path, help="Optional explicit path to Concat executable.")
    parser.add_argument("--source-checkout", action="append", default=[], help="Optional local Concat git checkout path to inspect for Cargo build.")
    parser.add_argument("--out", type=Path, help="Optional path to write ENV_MATRIX JSON.")
    args = parser.parse_args(argv)

    result = probe_host_environment(
        explicit_binary=args.concat_binary,
        source_checkouts=args.source_checkout or None,
    )
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    if args.json or not args.out:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
