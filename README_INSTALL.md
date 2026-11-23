# Installation & Cross-Platform Setup Guide (`video-director-concat`)

This single global skill serves **Windows x64**, **macOS Apple Silicon (`arm64`)**, and **macOS Intel (`x86_64`)** from one shared Creative Director architecture and one Concat MCP engine. Do **not** fork this into separate OS-specific skills.

## 1. Cross-Platform Support Matrix

| Dimension | Windows x64 | macOS Apple Silicon (`arm64`) | macOS Intel (`x86_64`) |
| --- | --- | --- | --- |
| **Global Skill Path** | `%USERPROFILE%\.gemini\config\skills\video-director-concat\` | `~/.gemini/config/skills/video-director-concat/` | `~/.gemini/config/skills/video-director-concat/` |
| **Workspace Skill Path (optional)** | `<workspace>\.agents\skills\video-director-concat\` | `<workspace>/.agents/skills/video-director-concat/` | `<workspace>/.agents/skills/video-director-concat/` |
| **Antigravity MCP Config** | Discover live runtime config (typically `%USERPROFILE%\.gemini\config\mcp_config.json`) | Discover live runtime config (typically `~/.gemini/config/mcp_config.json`) | Discover live runtime config (typically `~/.gemini/config/mcp_config.json`) |
| **Official Concat Asset** | `Concat-<ver>-windows-x86_64-setup.exe` or `.msi` | `Concat-<ver>-macos-arm64.dmg` | `Concat-<ver>-macos-x86_64.dmg` |
| **Concat Binary Path** | `C:\Program Files\Concat\concat.exe` or `%LOCALAPPDATA%\Programs\Concat\concat.exe` | `/Applications/Concat.app/Contents/MacOS/concat` | `/Applications/Concat.app/Contents/MacOS/concat` |
| **Deterministic MCP Launch** | `"args": ["--mcp", "headless"]` | `"args": ["--mcp", "headless"]` | `"args": ["--mcp", "headless"]` |
| **`CONCAT_MCP_ROOTS` Separator** | Semicolon (`;`) | Colon (`:`) | Colon (`:`) |
| **Security / Unsigned App Gate** | SmartScreen / UAC (owner approval; never disable Defender/UAC) | Gatekeeper / Quarantine (owner approval via Open Anyway; never disable Gatekeeper/SIP or auto-run `xattr`) | Gatekeeper / Quarantine (same policy) |
| **OS Minimum (per official docs)** | Windows 10/11 64-bit | macOS 12+ | macOS 12+ (ONNX cutout/Enhance/Chatterbox need macOS 13.4+) |
| **GPU / Acceleration** | DirectX 12 GPU (CPU fallback) | Metal GPU + Unified Memory (monitor memory pressure) | Metal GPU or CPU fallback |
| **Local TTS Fallback** | Audited Kokoro local WAV -> `media_import` | Audited Kokoro local WAV (benchmark CPU vs MPS/CoreML) -> `media_import` | Audited Kokoro CPU/small model or approved WAV (respect macOS 13.4+ ONNX limit) |
| **Media Probing Concurrency** | Process-isolated `ffprobe` (avoid multithreaded C DLLs like MediaInfo) | Bounded `ffprobe` subprocesses (single-writer for Concat exports) | Bounded `ffprobe` subprocesses (tighter RAM cap on low-RAM Macs) |
| **Unsupported Flag** | `UNSUPPORTED_CURRENT_VERSION` / `BLOCKED_ENV` | `UNSUPPORTED_CURRENT_VERSION` / `TCC_OR_FS_PERMISSION_BLOCKED` / `PENDING_OWNER_SECURITY_APPROVAL` | Same + `BLOCKED_OS_VERSION` / `ONNX_REQUIRES_MACOS_13_4` |

## 2. Install Concat (Official Provenance First)

Always fetch only from official GitHub Releases (`https://github.com/jub0t/Concat/releases`) and verify the asset digest against official `SHA256SUMS`.

### macOS (`arm64` / `x86_64`)

1. Detect architecture: `uname -m` (`arm64` -> `Concat-<version>-macos-arm64.dmg`, `x86_64` -> `Concat-<version>-macos-x86_64.dmg`).
2. Verify SHA-256 against official `SHA256SUMS`:
   ```sh
   shasum -a 256 ~/Downloads/Concat-<version>-macos-<arch>.dmg
   ```
3. Mount the `.dmg` and drag `Concat.app` to `/Applications` using the standard GUI workflow (no `sudo` unless explicitly justified).
4. Handle unsigned app warning via owner-approved macOS Privacy & Security (**Open Anyway**). Do **not** run `spctl --master-disable`, `csrutil disable`, or automatic `xattr -dr com.apple.quarantine` without explicit owner approval.
5. Verify executable:
   ```sh
   ls -la /Applications/Concat.app/Contents/MacOS/concat
   ```

### Windows (`x86_64`)

1. Download `Concat-<version>-windows-x86_64-setup.exe` or `.msi` from official GitHub Releases.
2. Verify SHA-256 against official `SHA256SUMS`:
   ```powershell
   Get-FileHash .\Concat-<version>-windows-x86_64-setup.exe -Algorithm SHA256
   ```
3. Complete installation with owner SmartScreen/UAC approval (never disable Defender/SmartScreen/UAC).
4. Confirm exact installed path (`C:\Program Files\Concat\concat.exe` or `%LOCALAPPDATA%\Programs\Concat\concat.exe`).

## 3. Configure Antigravity MCP (Discover -> Backup -> Merge)

Never overwrite an existing MCP config blindly. First run:

```sh
python3 scripts/platform_adapter.py --json
```

Back up the discovered `mcp_config.json`, then merge **only** the `concat` entry under `mcpServers` using exact expanded paths (do not rely on `%ENV%` expansion inside JSON).

### macOS Template (`~/.gemini/config/mcp_config.json`)

```json
{
  "mcpServers": {
    "concat": {
      "command": "/Applications/Concat.app/Contents/MacOS/concat",
      "args": ["--mcp", "headless"],
      "env": {
        "CONCAT_MCP_ROOTS": "/Users/<local-user>/Movies/AntigravityConcat"
      }
    }
  }
}
```

If reading footage from an external macOS volume, separate exact minimal roots with `:`:
`"/Volumes/<DiskName>/<FootageFolder>:/Users/<local-user>/Movies/AntigravityConcat"` (never allowlist `/`, `/Users`, `/Volumes`, or iCloud Drive wholesale).

### Windows Template (`%USERPROFILE%\.gemini\config\mcp_config.json`)

```json
{
  "mcpServers": {
    "concat": {
      "command": "C:\\Program Files\\Concat\\concat.exe",
      "args": ["--mcp", "headless"],
      "env": {
        "CONCAT_MCP_ROOTS": "D:\\Footage\\Campaign;D:\\AntigravityConcat\\Runs"
      }
    }
  }
}
```

## 4. Validate & Install Global Skill

1. Validate the staged package before publishing:
   ```sh
   python3 scripts/check_skill_package.py --skill-dir ./video-director-concat
   pytest ./video-director-concat/tests
   ```
2. Check for existing `video-director-concat` installations (backup with timestamp if updating; never create duplicate copies across global and workspace roots).
3. Copy validated tree to `~/.gemini/config/skills/video-director-concat/` (macOS) or `%USERPROFILE%\.gemini\config\skills\video-director-concat\` (Windows) and verify every file SHA-256 against `MANIFEST.json`.
4. Open a **fresh** Antigravity session and confirm `video-director-concat` appears once in discovered skills. If the active session has not reloaded skills yet, report `SKILL_DISCOVERED_PENDING_RESTART` / `ACTIVATION_PENDING_NEW_SESSION`.

## 5. Post-Install Verification Checklist

- [ ] `python3 scripts/platform_adapter.py --json` detects OS, arch, disk, RAM, `ffprobe`, and Concat binary cleanly.
- [ ] MCP handshake (`initialize`, `ping`, `tools/list`, `concat_version`) returns actual `version` and `mcp.mode=headless`.
- [ ] Gate C1 smoke test (10–15s native project -> preview -> save/close/reopen -> real Concat MP4 export -> `verify_export.py`) passes with evidence.
- [ ] No existing CapCut data, skills, or plugins were modified.
