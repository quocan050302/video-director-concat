# Windows Platform Adapter

When `platform.system() == "Windows"`, apply these Windows-specific operational rules alongside the shared Creative Director, Concat MCP, and Gate C0–C4 contracts.

## 1. Environment Probe & Binary Discovery

- Probe OS build, architecture (`AMD64` / `x86_64`), logical CPU cores, available RAM, GPU/VRAM if accessible, free disk space on both system and media/output drives, `ffprobe`, `ffmpeg`, `python`, and `git`.
- Check official Concat install locations only:
  - Machine-wide (`.msi` / all users): `C:\Program Files\Concat\concat.exe`
  - Per-user (setup `.exe`): `%LOCALAPPDATA%\Programs\Concat\concat.exe`
- Confirm binary identity and version via actual execution/metadata; never assume another executable named `concat` is the Concat video editor.

## 2. Security, SmartScreen & UAC

- Download only official GitHub Releases assets (`Concat-<ver>-windows-x86_64-setup.exe` or `.msi`) and verify SHA-256 against official `SHA256SUMS`.
- Official Windows releases may be unsigned. Never disable SmartScreen, Windows Defender, Firewall, or UAC, and never run `irm ... | iex` or untrusted PowerShell install scripts.
- If SmartScreen/UAC prompts appear, stop at `PENDING_OWNER_SECURITY_APPROVAL` and let the machine owner approve installation directly.

## 3. Global Skill & MCP Configuration

- **Global skill path**: `%USERPROFILE%\.gemini\config\skills\video-director-concat\SKILL.md` (or actual discovered Antigravity global skill root).
- **MCP config**: Discover the live Antigravity `mcp_config.json`, back it up, and merge only `mcpServers.concat`.
- Use **full expanded paths** with escaped backslashes (`"C:\\Program Files\\Concat\\concat.exe"`) — never assume `%LOCALAPPDATA%` expands inside JSON unless proven by the MCP client.
- Launch mode: `["--mcp", "headless"]` for deterministic runs.
- **`CONCAT_MCP_ROOTS`**: Separated by semicolon (`;`). Allowlist only the exact media input directory and safe run/output directory (e.g., `D:\Footage\Campaign;D:\AntigravityConcat\Runs`) — never `C:\` or `D:\` wholesale.

## 4. Concurrency, Native Libraries & Filesystem Safety

- Prefer process-isolated `ffprobe` subprocesses over multithreaded native C DLL bindings (such as `pymediainfo`) to avoid Windows DLL thread-safety crashes and file handle locking.
- Pass all external commands as argument lists (`subprocess.run([...])`) — never raw PowerShell/cmd string interpolation on untrusted or Unicode filenames.
- Respect `concat.lock` and Windows open-file locks; never force-delete lock files or terminate unrelated user `concat.exe` processes.
- Keep source and output paths distinct; verify sufficient free disk space on the target drive before staging, caching, or exporting.
- Preserve all existing CapCut installations, projects, skills (`video-director-capcut`), and plugins completely untouched as an archive.
