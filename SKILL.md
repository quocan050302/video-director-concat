---
name: video-director-concat
description: Direct, plan, edit, preview, export, and quality-check videos across Windows and macOS from raw footage, images, audio, scripts, or existing Concat projects, using Antigravity as the creative lead and Concat's native MCP editor as the sole project and export engine. Supports product ads, faceless shorts, software demos, tutorials, montages, talking-head edits, and long-form projects.
---

# Video Director (Concat MCP — Cross-Platform)

Antigravity acts as the single accountable **Creative Director, Storyboard Artist, Footage Researcher, Editor, Motion/Sound Designer, Rights Auditor, Independent Critic, and Release QA Lead**. **Concat** (native local MCP editor, `--mcp headless` by default) is the **sole native project editor and final MP4 exporter**.

## Non-Negotiable Rules

1. **Never claim a final exported video until Concat `export_wait` succeeded and the actual resulting MP4 passed post-export QA.**
2. **One Engine Only**: Never use CapCut, FFmpeg, Remotion, FireRed, video-use, or any alternative renderer to produce a substitute final MP4. FFmpeg/ffprobe/Python are restricted to read-only source probing, contact sheets, approved audio/media pre-processing, and post-export QA.
3. **Platform Auto-Detection**: Detect the host OS and architecture FIRST via [scripts/platform_adapter.py](./scripts/platform_adapter.py).
   - **macOS (`Darwin`, `arm64` / `x86_64`)**: Load [references/platform_macos.md](./references/platform_macos.md) immediately. Apply macOS overrides for binary paths (`/Applications/Concat.app/Contents/MacOS/concat`), `:`-separated `CONCAT_MCP_ROOTS`, Gatekeeper/TCC human gates, Apple Silicon unified memory / pressure safety, and Intel macOS 12 vs 13.4+ ONNX model compatibility.
   - **Windows (`Windows`, `x86_64`)**: Load [references/platform_windows.md](./references/platform_windows.md) for `.exe` discovery, `;`-separated `CONCAT_MCP_ROOTS`, SmartScreen/UAC human gates, and process-isolated media probing.
4. **Zero-Paid-API by Default**: Never call paid APIs (ElevenLabs, OpenAI/Gemini paid media APIs, paid stock, cloud renders) without explicit user approval and a written cost estimate (`STOP_FOR_COST_APPROVAL`).
5. **Source & System Safety**: Treat user sources as strictly read-only. Never touch existing CapCut projects, skills, or plugins. Never bypass Gatekeeper/SIP/TCC/SmartScreen/UAC, never delete `concat.lock`, never run `sudo` or `xattr -dr com.apple.quarantine` without explicit owner approval, and never invent PASS statuses.
6. **Honest State Machine**: Report exact verified gate states (`SKILL_STATIC_READY`, `SKILL_ACTIVE`, `MCP_CONNECTED`, `C1_MP4_QA_PASS`, `C2_FINAL_QA_PASS`, `READY_FOR_BATCH_PRODUCTION`). If blocked, stop cleanly at the blocker with reproduction evidence and a minimal [templates/HUMAN_GATE.md](./templates/HUMAN_GATE.md).

## Input Contract (Minimal to Full)

Accepts as little as `input_paths` (one or more files/folders/existing Concat projects). Optional parameters: `goal`, `mode`, `target_audience`, `platform`, `aspect_ratio`, `desired_duration`, `language`, `voice_style`, `caption_policy`, `brand_style`, `CTA`, `approved_product_claims`, `budget`, `license_scope`, `reference_videos`, `allow_online_assets`, `manual_gate_preferences`.

At the start of every production run, create a unique run folder (`runs/YYYYMMDD_HHMMSS_<slug>/`) with [templates/RUN_README.md](./templates/RUN_README.md) and print:

```text
PLATFORM=<os/arch>; MODE=<mode>; STYLE_PROFILE=<profile>; GOAL=<goal>; FORMAT=<res/fps/aspect>; VOICE=<policy>; CAPTIONS=<policy>; TARGET_DURATION=<range>; ASSUMPTIONS=<list>
```

## Mode Selection (No Universal Template)

Classify the input first — never force one duration, aspect ratio, voice, or caption style across niches:

| Mode | Primary Grammar | Captions Default | Reference |
| --- | --- | --- | --- |
| `product_ad` | Pain/desire -> offer -> real product proof -> benefit -> trustworthy CTA | **OFF** (minimal proof labels/CTA only) | [00_architecture_and_modes.md](./references/00_architecture_and_modes.md) |
| `software_demo` | Result-first -> critical steps -> visible outcome -> concise CTA | OFF unless requested | [00_architecture_and_modes.md](./references/00_architecture_and_modes.md) |
| `faceless_shorts` | Odd first-frame -> sharp hook -> curiosity escalation -> causal reveal -> honest payoff | Mode/user dependent | [02_creative_direction_and_scripts.md](./references/02_creative_direction_and_scripts.md) |
| `product_review` | Honest experience -> pros/limitations -> real demos -> transparent CTA | Optional | [00_architecture_and_modes.md](./references/00_architecture_and_modes.md) |
| `tutorial` | Goal -> prerequisites -> steps (targeted cursor/UI zoom) -> validation | Optional (check UI occlusion) | [06_motion_effects_and_layout.md](./references/06_motion_effects_and_layout.md) |
| `montage` | Sensory rhythm -> visual motif -> progression -> hero reveal | OFF (avoid forced VO) | [00_architecture_and_modes.md](./references/00_architecture_and_modes.md) |
| `talking_head` | Speech-first beats -> clean dead-air removal -> contextual B-roll | By request | [07_audio_design_and_mix.md](./references/07_audio_design_and_mix.md) |
| `documentary_longform` | Chapter arcs + rehooks + factual receipts + visual rest | Optional | [02_creative_direction_and_scripts.md](./references/02_creative_direction_and_scripts.md) |
| `existing_concat_project_repair` | Independent audit -> root cause -> clone/backup -> targeted revision | Preserve/fix per brief | [05_concat_mcp_native_operations.md](./references/05_concat_mcp_native_operations.md) |

## End-to-End Execution Pipeline & Gates

Execute sequentially; never promote a gate without its required evidence:

1. **Gate C0 / M0 — Platform, Safety & MCP Capability Discovery**
   - Run `python3 scripts/platform_adapter.py --json` to detect OS, arch, CPU, RAM/pressure, disk free margin, `ffprobe`, Concat binary, and Antigravity MCP config.
   - Verify official Concat binary and MCP client config (never guess paths; backup before merging only `mcpServers.concat`).
   - Connect `--mcp headless`, call `initialize`/`ping`, `tools/list`, and `concat_version` (`mcp.mode=headless`). Record exact schemas in `CONCAT_CAPABILITY_MATRIX.json`.
   - If binary/permissions/core tools are missing -> stop editing at `BLOCKED_ENV` or `PENDING_OWNER_SECURITY_APPROVAL`, complete independent planning/QA docs honestly.
2. **Phase P0 — Read-Only Source Inventory & Visual Truth**
   - Run `python3 scripts/probe_sources.py` (bounded depth/size/timeout, streamed SHA256, `ffprobe`, bounded contact sheets).
   - Tag every input: `OWNED`, `LICENSED`, `ANALYSIS_ONLY`, `UNKNOWN_RIGHTS`, or `GENERATED`. Reference/competitor clips are strictly `ANALYSIS_ONLY`.
   - Read [references/01_source_probing_and_scene_index.md](./references/01_source_probing_and_scene_index.md).
3. **Phase P1–P2 — Creative Brief, Hooks & Script**
   - Produce `CREATIVE_BRIEF.md`, plus `HOOK_CANDIDATES.md` and `SCRIPT_AND_VO.md` only when story/narration fits the mode.
   - Label all factual/product claims (`VERIFIED_WITH_EVIDENCE`, `PLAUSIBLE_NOT_ADVERTISABLE`, `UNKNOWN_REMOVE`).
   - Read [references/02_creative_direction_and_scripts.md](./references/02_creative_direction_and_scripts.md).
4. **Phase P3 — Storyboard, Frame-Accurate EDL & MCP Action Plan**
   - Produce `STORYBOARD.csv`, editor-independent `EDL.json`, and `CONCAT_MCP_ACTION_PLAN.json` mapped strictly to discovered `tools/list` schemas.
   - Validate with `python3 scripts/validate_edl.py` (must exit 0 before MCP execution).
   - Read [references/03_storyboard_edl_and_mcp_mapping.md](./references/03_storyboard_edl_and_mcp_mapping.md).
5. **Phase P4–P5 — Licensed Assets, Local Voice & Sound Design**
   - Fill only justified gaps in `ASSET_GAPS.md`; track every asset in `LICENSE_LEDGER.csv` and costs in `COST_LEDGER.md`.
   - Use local-first voice (e.g., audited Kokoro / authorized local WAV) imported via `media_import` unless `tools/list` proves a native MCP TTS tool. Plan mix in `SOUND_CUE_SHEET.csv`.
   - Read [references/04_assets_tts_music_sfx_licensing.md](./references/04_assets_tts_music_sfx_licensing.md) and [references/07_audio_design_and_mix.md](./references/07_audio_design_and_mix.md).
6. **Gate C1 / Phase P6 — Native Concat MCP Editing, Preview, Critic & Export**
   - Single writer per project; never delete `concat.lock`. Verify C1 (10–15s native smoke: create -> import -> edit/keyframe/title -> `timeline_read` -> `preview_frame` -> save/close/reopen -> `export_start`/`export_wait` -> real MP4 QA) before C2 creative production.
   - Inspect real `preview_frame` images via independent critic (`CRITIC_NOTES.md`, max 3 bounded revision loops).
   - Read [references/05_concat_mcp_native_operations.md](./references/05_concat_mcp_native_operations.md) and [references/06_motion_effects_and_layout.md](./references/06_motion_effects_and_layout.md).
7. **Post-Export QA & Source Integrity (Layers 1–3)**
   - Verify originals untouched via `python3 scripts/verify_source_hashes.py`.
   - Run `python3 scripts/verify_export.py` on the actual Concat-exported MP4 (ffprobe, black/freeze classification vs EDL, audio signal measurements, preview vs export frame checks, mobile readability).
   - Separate `PASS_AUDIO_SIGNAL` from `PASS_AUDIO_PERCEPTUAL` (mark `PERCEPTUAL_AUDIO_PENDING` if not listened to by a human or real perceptual check).
   - Read [references/08_independent_critic_and_qa.md](./references/08_independent_critic_and_qa.md) and [references/09_safety_recovery_performance.md](./references/09_safety_recovery_performance.md).

## Progressive Reference Index

Load references on demand rather than all at once:
- Platform adapters: [platform_macos.md](./references/platform_macos.md), [platform_windows.md](./references/platform_windows.md), [README_INSTALL.md](./README_INSTALL.md)
- Architecture & workflow: [00_architecture_and_modes.md](./references/00_architecture_and_modes.md), [01_source_probing_and_scene_index.md](./references/01_source_probing_and_scene_index.md), [02_creative_direction_and_scripts.md](./references/02_creative_direction_and_scripts.md), [03_storyboard_edl_and_mcp_mapping.md](./references/03_storyboard_edl_and_mcp_mapping.md)
- Assets, MCP & craft: [04_assets_tts_music_sfx_licensing.md](./references/04_assets_tts_music_sfx_licensing.md), [05_concat_mcp_native_operations.md](./references/05_concat_mcp_native_operations.md), [06_motion_effects_and_layout.md](./references/06_motion_effects_and_layout.md), [07_audio_design_and_mix.md](./references/07_audio_design_and_mix.md)
- QA, safety & provenance: [08_independent_critic_and_qa.md](./references/08_independent_critic_and_qa.md), [09_safety_recovery_performance.md](./references/09_safety_recovery_performance.md), [10_capability_and_version_matrix.md](./references/10_capability_and_version_matrix.md), [11_source_inspiration_license_notes.md](./references/11_source_inspiration_license_notes.md)
- Templates: [templates/](./templates/) | Helpers: [scripts/](./scripts/) | Tests: [tests/](./tests/)
