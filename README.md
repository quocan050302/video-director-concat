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
├── references/               # 13 core workflow & KH-01 references + macOS/Windows platform adapters
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

### Hardened Validation Contracts (QA.R1–QA.R3)

- **EDL (`scripts/validate_edl.py`)**: Clean 3-tier modes (`--validation-mode draft | structural | release` + `--gate-phase C1|C2|C4`). Release (`PASS_EDL_VALID_FOR_RELEASE`, `release_ready=true`) requires duplicate-free inventory/ledger, `--run-dir` + `#fragment` anchor verification, archived `license_evidence_path`, separate `GENERATED` code+weights/voice licenses, AND per-file verified on-disk `PASS_SOURCE_INTEGRITY` (`expected_sha256 == actual_sha256 == inventory.sha256`, mandatory on C2/C4). Without source integrity, `--validation-mode structural` returns `PASS_EDL_STRUCTURAL_ONLY` (`release_ready=false`).
- **Export QA (`scripts/verify_export.py`)**: Separates `--qa-level technical` (`PASS_TECHNICAL_ONLY`) from `--qa-level release --gate-phase C1|C2|C4 --release-policy technical-smoke|full-creative`. Requires `LIVE_MCP_EXPORT_EVIDENCE` backed by on-disk `MCP_RAW_TRACE.jsonl` (`raw_transcript_path` + `raw_transcript_sha256` -> `LIVE_OBSERVED_WITH_RAW_TRANSCRIPT`), mandatory `started_at`/`completed_at` timestamps, per-step `project_id` consistency, `CONCAT_MCP_PREVIEW_FRAME` origin + SSIM/PSNR, full planned audio enforcement (`audio_expected_by_plan` covering VO, BGM, SFX, ambience), EOF freeze/silence detection, EBU R128 LUFS/true-peak measurement, and content-aware `OWNER_HUMAN` (`OWNER_INTERACTION_RECORDED`, `reviewed_at >= exported_at`) perceptual audio confirmation.
- **Source Discovery & Integrity (`scripts/probe_sources.py`, `scripts/verify_source_hashes.py`)**: True streaming `os.scandir` traversal, explicit `INCOMPLETE_SOURCE_INVENTORY` (exit `2`) when budgets/permissions truncate discovery, multi-root disambiguation (`R01/...`), collision-free contact sheets, and hardened multi-root SHA-256 verification rejecting POSIX/Windows traversal, symlinks, non-regular files, and duplicate IDs.
- **Platform Discovery (`scripts/platform_adapter.py`)**: Supports official bundles, `CONCAT_BINARY`, `PATH`, and local source-built Cargo binaries (`--source-checkout`), with decoupled OS, disk (`DISK_OK`/`DISK_WARN`/`DISK_BLOCK`), binary, QA-tool, and MCP statuses.

### Install as Antigravity Global Skill

- **macOS**: Copy this directory (excluding `.git`) to `~/.gemini/config/skills/video-director-concat/`
- **Windows**: Copy this directory (excluding `.git`) to `%USERPROFILE%\.gemini\config\skills\video-director-concat\`

## License & Provenance Notes

- Engine integration targets [jub0t/Concat](https://github.com/jub0t/Concat) (`AGPL-3.0-or-later` / commercial dual license). Concat itself is not bundled in this repository.
- See [`references/11_source_inspiration_license_notes.md`](./references/11_source_inspiration_license_notes.md) for the full attribution and license audit of conceptual planning references.
