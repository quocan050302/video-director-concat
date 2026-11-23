# `video-director-concat` — Cross-Platform Antigravity Global Skill (Windows & macOS)

One reusable cross-platform **Antigravity Creative Director** global skill that plans, edits, previews, exports, and quality-checks videos across **Windows x64**, **macOS Apple Silicon (`arm64`)**, and **macOS Intel (`x86_64`)** using **Concat's native MCP editor (`--mcp headless`)** as the sole native project and final MP4 export engine.

## Highlights

- **Single Cross-Platform Skill**: Automatically detects host OS and CPU architecture via [`scripts/platform_adapter.py`](./scripts/platform_adapter.py) and applies platform-specific overrides:
  - **macOS (`Darwin`, `arm64` / `x86_64`)**: [`references/platform_macos.md`](./references/platform_macos.md) (`/Applications/Concat.app/Contents/MacOS/concat --mcp headless`, `:`-separated `CONCAT_MCP_ROOTS`, Gatekeeper/TCC human gates, Apple Silicon unified memory pressure, Intel macOS 12 vs 13.4+ ONNX model note).
  - **Windows (`Windows`, `x86_64`)**: [`references/platform_windows.md`](./references/platform_windows.md) (`concat.exe --mcp headless`, `;`-separated `CONCAT_MCP_ROOTS`, SmartScreen/UAC human gates, process-isolated `ffprobe`).
- **One Native Video Engine Only**: Concat MCP is the sole project editor and final MP4 exporter. No CapCut in the new pipeline and no silent FFmpeg/third-party renderer fallback.
- **Creative Director Across Niches**: Mode classification (`product_ad`, `software_demo`, `faceless_shorts`, `product_review`, `tutorial`, `montage`, `talking_head`, `documentary_longform`, `existing_concat_project_repair`) — no one-size-fits-all template.
- **Strict Gates (C0–C4 + M0) & Fail-Closed QA**:
  - Read-only source probing with streamed SHA-256 verification (`scripts/probe_sources.py`, `scripts/verify_source_hashes.py`).
  - Frame-accurate editor-independent EDL & rights validation (`scripts/validate_edl.py`).
  - Fail-closed post-export MP4 QA separating `PASS_AUDIO_SIGNAL` from `PASS_AUDIO_PERCEPTUAL` (`scripts/verify_export.py`).
  - Zero paid APIs by default (`COST_LEDGER.md` + `STOP_FOR_COST_APPROVAL`).

## Repository Layout

```text
video-director-concat/
├── SKILL.md                  # Global skill entry point & YAML frontmatter
├── README.md                 # Repository overview
├── README_INSTALL.md         # Windows x64 / macOS arm64 / macOS x86_64 install matrix
├── MANIFEST.json             # Non-self-referential file inventory & SHA-256 hashes
├── references/               # 12 core workflow references + macOS/Windows platform adapters
├── templates/                # 15 structured creative, rights, MCP plan, QA & human-gate templates
├── scripts/                  # Pure Python stdlib platform adapter, probe, validator & QA helpers
└── tests/                    # Automated static, EDL contract, read-only, platform & no-false-PASS tests
```

## Quick Install & Verification

See [`README_INSTALL.md`](./README_INSTALL.md) for the complete Windows/macOS installation guide (including official Concat SHA-256 verification, Gatekeeper/SmartScreen human gates, and safe `mcp_config.json` merging).

### Validate Package & Run Tests

```sh
python3 scripts/check_skill_package.py --skill-dir .
python3 -m pytest -v tests
python3 scripts/platform_adapter.py --json
```

### Hardened Validation Contracts (QA.R1 & QA.R2)

- **EDL (`scripts/validate_edl.py`)**: Default `--validation-mode release --run-dir <dir>` fails closed on duplicate inventory/ledger keys, missing `run_dir`, missing `#fragment` anchor content, Windows/POSIX path traversal, `license_url`-only claims without archived `license_evidence_path`, and `GENERATED` assets missing separate code + weights/voice licenses. Supports `--source-integrity <json> --require-source-integrity` for on-disk C2 source verification. Planning drafts use `--validation-mode draft` (`PASS_EDL_DRAFT_ONLY`).
- **Export QA (`scripts/verify_export.py`)**: Separates `--qa-level technical` (`PASS_TECHNICAL_ONLY`) from `--qa-level release --gate-phase C1|C2|C4 --release-policy technical-smoke|full-creative`. Distinguishes `LIVE_MCP_EXPORT_EVIDENCE` from `UNIT_SIMULATED_PROVENANCE`, checks full `tool_trace`, matched `export_start`/`export_wait` job IDs, `CONCAT_MCP_PREVIEW_FRAME` preview origin + SSIM/PSNR, EOF freeze/silence detection, mandatory EBU R128 LUFS/true-peak measurement, and `OWNER_HUMAN` perceptual audio confirmation (restricting `technical-smoke` strictly to C1).
- **Source Discovery & Integrity (`scripts/probe_sources.py`, `scripts/verify_source_hashes.py`)**: True streaming `os.scandir` traversal (no unbounded `sorted(scandir)`), explicit `INCOMPLETE_SOURCE_INVENTORY` (exit `2`) whenever scan budgets or permissions truncate discovery, multi-root disambiguation (`R01/...`), collision-free contact sheets, and multi-root SHA-256 verification (`--root R01=...`).
- **Platform Discovery (`scripts/platform_adapter.py`)**: Supports official bundles, `CONCAT_BINARY`, `PATH`, and local source-built Cargo binaries (`--source-checkout`), with decoupled OS, disk (`DISK_OK`/`DISK_WARN`/`DISK_BLOCK`), binary, QA-tool, and MCP statuses.

### Install as Antigravity Global Skill

- **macOS**: Copy this directory (excluding `.git`) to `~/.gemini/config/skills/video-director-concat/`
- **Windows**: Copy this directory (excluding `.git`) to `%USERPROFILE%\.gemini\config\skills\video-director-concat\`

## License & Provenance Notes

- Engine integration targets [jub0t/Concat](https://github.com/jub0t/Concat) (`AGPL-3.0-or-later` / commercial dual license). Concat itself is not bundled in this repository.
- See [`references/11_source_inspiration_license_notes.md`](./references/11_source_inspiration_license_notes.md) for the full attribution and license audit of conceptual planning references.
