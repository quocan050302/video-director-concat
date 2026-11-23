# macOS Platform Adapter (`AG-VIDEO-DIRECTOR-CONCAT-MACOS-01`)

When `platform.system() == "Darwin"` (`uname -s == Darwin`), these macOS rules **override** all Windows-only details in the master workflow while preserving creative direction, rights governance, Concat-only export, and Gates C0–C4.

## 1. Gate M0 — Mandatory Read-Only Environment Probe

Run `python3 scripts/platform_adapter.py --json` (or bounded read-only shell probes: `sw_vers`, `uname -s`, `uname -m`, `sysctl -n hw.logicalcpu`, `sysctl -n hw.memsize`, `vm_stat`, `df -h "$HOME"`, `command -v shasum python3 ffprobe ffmpeg`, bounded `system_profiler SPHardwareDataType SPDisplaysDataType`).

Record the mandatory `ENV_MATRIX`:
`os_version`, `arch` (`arm64` vs `x86_64`), `cpu_cores`, `ram_total`, `ram_available_or_unknown`, `gpu_model_or_unknown`, `metal_capability_or_unknown`, `disk_free`, `app_binary`, `app_arch`, `app_version`, `model_compatibility`, `ffprobe_version_or_missing`, `mcp_client_runtime`, `time_checked`.

### Version & Hardware Compatibility (Official Docs — Verify on Host)
- **macOS 12+**: Minimum for Concat Apple Silicon (`arm64`) and Intel (`x86_64`) desktop builds. Below macOS 12 -> `BLOCKED_OS_VERSION`.
- **Intel macOS 12 caveat**: ONNX-dependent optional features (cutout/background removal, Enhance, Chatterbox) require **macOS 13.4+**. Do not misclassify an optional ONNX model restriction as a general MCP failure.
- **Hardware**: 64-bit CPU, 4 GB minimum RAM; 6+ cores and 16 GB RAM recommended for 4K timelines and larger models (recommended, not a hard floor). Metal GPU accelerates preview/compositing; CPU fallback exists with host-dependent speed.
- **Never** require WSL, Wine, VM, or Rosetta to work around Windows assumptions; Concat ships native macOS `arm64` and `x86_64` DMGs. Only consider Rosetta if explicitly proven necessary, approved by the owner, and QA'd separately.

## 2. Binary Discovery, Security & Gatekeeper Policy

- **Asset selection by `uname -m`**:
  - `arm64` -> `Concat-<version>-macos-arm64.dmg`
  - `x86_64` -> `Concat-<version>-macos-x86_64.dmg`
- **Verified executable**: `/Applications/Concat.app/Contents/MacOS/concat` (never `concat.exe`; never guess if absent).
- **Security rules**:
  - Verify official GitHub Releases URL and SHA-256 against official `SHA256SUMS`.
  - Never silently download and execute untrusted binaries; stop at `PENDING_OWNER_SECURITY_APPROVAL` when owner confirmation or DMG install is needed.
  - Install via standard GUI drag to `/Applications`; avoid `sudo` without documented approval.
  - **Gatekeeper / Quarantine**: Official macOS builds may be unsigned. Prefer owner verification and macOS **Privacy & Security -> Open Anyway**.
  - **Forbidden by default**: Never run `spctl --master-disable`, `csrutil disable`, bulk `xattr` removal, or auto-script `xattr -dr com.apple.quarantine /Applications/Concat.app`. Only execute `xattr` if the machine owner explicitly approves it after verifying the official hash.

## 3. Concat MCP on macOS

- **Deterministic command**: `/Applications/Concat.app/Contents/MacOS/concat` with `args: ["--mcp", "headless"]`.
- **Window mode (`--mcp window`)**: Opt-in only when Concat GUI is open, **Settings > Automation > Scripts and apps** is enabled, and the user explicitly needs window mediation. Never use `--mcp auto` for release QA.
- **MCP config discovery**: Inspect `~/.gemini/config/mcp_config.json` (and verify any symlink from `~/.gemini/antigravity/mcp_config.json`). Backup before merging only `mcpServers.concat`.
- **`CONCAT_MCP_ROOTS`**:
  - Separator on macOS is colon (`:`), **not** `;`.
  - Prefer `$HOME/Movies/AntigravityConcat/` or `$HOME/Projects/AntigravityConcat/` so runs stay inside `$HOME`.
  - Set `CONCAT_MCP_ROOTS` inside MCP client config `env` (GUI/launchd MCP hosts do not inherit interactive Terminal `export`s).
  - Allowlist exact directories only — never `/`, `/Users`, `/Volumes`, or iCloud Drive wholesale.
- **Locking**: Respect `concat.lock`; never force-delete locks or kill user GUI Concat processes.

## 4. macOS Privacy (TCC) & Filesystem Safety

- Protected locations (`Desktop`, `Documents`, `Downloads`, Photos/iCloud, `/Volumes/<External>`, network shares) are guarded by macOS TCC.
- Never request or force Full Disk Access; never mutate TCC databases (`tccutil`/SQLite); never work around `Operation not permitted` with `sudo` or `chmod -R 777`. Record `TCC_OR_FS_PERMISSION_BLOCKED` and give the owner the narrowest Privacy & Security toggle required.
- Microphone / Screen Recording permissions are ONLY needed for live capture — importing existing files does not require them.
- Verify external volumes are mounted and readable before import; prefer copy-on-write/hashed staging inside `$HOME` (never deleting originals; reject symlink escapes).
- Avoid iCloud Drive, Dropbox, or SMB shares for active Concat project writes or scratch caches unless explicitly approved and tested for atomic lock/rename safety.
- APFS supports atomic rename within the same volume; cross-volume moves (e.g., APFS <-> exFAT) must copy + SHA-256 verify before publish.

## 5. Audio / TTS & Performance on Apple Silicon vs Intel

- **Local TTS**: Check `tools/list` first; if no MCP TTS tool is exposed, generate audited local WAV (e.g., Kokoro local) and import via `media_import`. Avoid downloading duplicate Kokoro models (built-in Concat + Python package).
- **Apple Silicon**: Benchmark actual CPU vs MPS/CoreML latency and peak memory rather than assuming every Python TTS library accelerates on MPS/ANE. Monitor **memory pressure and swap** (`vm_stat` / RSS) because unified memory is shared by CPU and GPU.
- **Intel Mac**: Honor macOS 13.4+ ONNX requirement; cap chunk sizes and concurrency on <=8 GB RAM systems; do not download 1.1 GB voice models unless justified.
- **System Voice (`say`)**: Not a default production voice; use only as an explicitly approved fallback with license/quality notes.
- **Concurrency**: Bounded parallel read-only `ffprobe`/SHA-256/contact-sheet probes only; strictly single-writer per Concat project and single concurrent Metal/VideoToolbox export.
- **Media edge cases**: Test Vietnamese Unicode filenames, spaces, quotes, emoji (always pass argv arrays, never shell interpolation), iPhone HEVC/MOV, VFR, rotation metadata, HDR/10-bit conversion, and preserve originals if pre-transcoding is required.
