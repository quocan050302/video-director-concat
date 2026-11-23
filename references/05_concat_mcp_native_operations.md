# 05 — Concat MCP Native Operations & Verification Contract

Concat exposes its native engine over **newline-delimited JSON-RPC 2.0 on stdio** (`concat --mcp headless`). Standard output carries protocol frames only; logs go to stderr.

## 1. Runtime Discovery Rule

**Never hardcode speculative tool names or JSON arguments from documentation alone.** On every new Concat version or host:
1. Run `initialize` -> `ping` -> `tools/list` -> `concat_version`.
2. Verify `mcp.mode == "headless"` (unless `window` mode was explicitly approved and verified) and record the exact `version`.
3. Persist discovered tool names and JSON schemas in `CONCAT_CAPABILITY_MATRIX.json`.
4. Fail fast (`BLOCKED_MCP_CAPABILITY`) if any required C1 core tool (`project_create`, `media_import`, `clip_add`/`clips_add_sequence`, `timeline_read`, `preview_frame`, `project_save`, `export_start`, `export_wait`) is missing.

## 2. Core Native Tool Verification Table

| MCP Tool (Verify in `tools/list`) | Role | Mandatory Verification / Postcondition |
| --- | --- | --- |
| `concat_version` | Handshake proof | Exact engine version, `mcp.mode=headless`, protocol status |
| `project_create` / `project_list` | Project lifecycle | Unique project ID & isolated folder under allowed root, no collision |
| `project_set_video` | Output canvas spec | Readback agrees on width, height, FPS, aspect |
| `media_probe` | Engine media inspect | Agrees with independent `ffprobe` (dimensions, duration, streams) |
| `media_import` | Asset ingestion | Valid asset ID returned; rights pre-checked (`OWNED`/`LICENSED`/`GENERATED` only) |
| `track_add` / `timeline_linkage` | Track topology | Explicit video/overlay/audio lane roles and linkage state |
| `clip_add` / `clips_add_sequence` | Timeline assembly | Ordered clip IDs, valid source in/out, expected timeline timestamps |
| `clip_trim` / `clips_split` | Precision editing | No negative/out-of-range bounds; verified via `timeline_read` |
| `clips_move` / `clip_speed` / `clip_update` | Pacing & timing | Expected duration update; no unintended gaps or collisions |
| `clip_transform` / `clip_frame` / `timeline_background` | Framing & layout | Crop/scale/position/background visually verified in `preview_frame` |
| `keyframe_set` / `keyframe_clear` | Motion animation | Property name valid; fractional clip position `0..1` per schema; movement verified across >=2 frames |
| `title_add` / `title_style_words` / `captions_add` | Typography | Legible in safe zone, verified font rights, contrast checked in preview |
| `effects_list` / `effect_layer_add` / `effect_key_set` | Effects & transitions | Use ONLY IDs returned by `effects_list`; verify visual survival in preview AND MP4 |
| `edit_apply` / `edit_undo` / `edit_redo` | Atomic batches | Use for bounded scene batches only after testing undo semantics |
| `timeline_read` / `project_get` | Authoritative state | Concise readback (`timeline_read`) after major edits; `project_get` for full schema audit |
| `preview_frame` | Visual inspection | Actual returned composited PNG/image saved and inspected by critic (proves visuals, NOT audio) |
| `project_save` / `project_close` / `project_open` | Edit persistence | Save -> close -> reopen -> semantic timeline fingerprint matches; project remains editable |
| `export_start` / `export_status` / `export_wait` | Final MP4 export | Bounded timeout, progress tracked, completed status, exact MP4 path exists and passes `verify_export.py` |
| `export_cancel` | Safe abort | Cleanly aborts hung/failed export; partial artifacts quarantined, never promoted |

## 3. Locking, Memory & Idempotency Rules

- **In-RAM edits**: Timeline changes live in memory until `project_save` succeeds. Checkpoint with `project_save` after each major phase.
- **Project locks (`concat.lock`)**: Single writer per project. If a project is open in Concat GUI, headless mode refuses it — **never** delete `concat.lock` or kill the user's GUI window.
- **No blind retries on non-idempotent ops**: If a `clip_add` or `title_add` times out, call `timeline_read` first to reconcile existing IDs before retrying. Cap targeted retries at 2.
- **Missing GUI features**: GUI features (e.g., built-in TTS, certain masks/captions) are NOT assumed available in MCP unless present in `tools/list` and tested. Document gaps in `MCP_LIMITATION.md` and use compliant fallbacks (e.g., local WAV -> `media_import`, clean hard cuts).

## 4. Live Provenance vs Unit Fixture Separation (`QA.R2`)

- **Strict Provenance Source Tagging**:
  - `LIVE_MCP_EXPORT_EVIDENCE`: Captured directly from actual live Concat MCP `tools/call` replies during the current run. Must include `concat_binary_sha256`, `project_path` inside `allowed_project_root` (no symlink), `tool_trace` covering `project_create`, `timeline_read`, `preview_frame`, `project_save`, `project_close`, `project_open`, `export_start`, and `export_wait`, matching non-empty `export_start.job_id == export_wait.job_id` (unless explicit `WAIT_OMITS_JOB_ID_CORRELATED` schema variant with `request_correlation_id` is proven from live `tools/list`), plausible timestamp ordering, identical `timeline_fingerprint_before_save == timeline_fingerprint_after_reopen`, non-symlink `output_path` inside `allowed_export_root`, and previews tagged `origin: "CONCAT_MCP_PREVIEW_FRAME"` correlated to `preview_frame` `tool_call_id`s (never frames extracted from the exported MP4).
  - `UNIT_SIMULATED_PROVENANCE`: Allowed ONLY in offline unit tests validating schema consistency (`PASS_SCHEMA_CONSISTENCY_UNIT_ONLY`). Can **never** set `live_concat_verified: true` or `PASS_END_TO_END_EXPORT_QA`.
  - **Honest Trust Boundary**: JSON logs verify orchestrator consistency and on-disk artifact hashes; they are not external cryptographic attestation. Never redact/omit failed tool calls or inject auth tokens into logs.
