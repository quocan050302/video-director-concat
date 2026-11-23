# 10 — Concat Capability & Version Provenance Matrix

Never treat documentation claims as runtime proof. Every capability entry MUST carry an explicit provenance level, Concat version, OS/arch, and verification date.

## 1. Provenance Levels (Lowest -> Highest)

1. `DOC_CLAIM` — Mentioned in official Concat docs (`docs/MCP.md`, website guides, release notes); NOT yet executed on this machine.
2. `TOOLS_LIST_EXPOSED` — Returned live by `tools/list` on the installed Concat binary with parsed JSON schema.
3. `SMOKE_EXECUTED` — Invoked successfully via live `tools/call` with valid response.
4. `PREVIEW_CHECKED` — Visual result confirmed in an actual Concat `preview_frame` image.
5. `REOPEN_CHECKED` — Edit survived `project_save` -> `project_close` -> `project_open` -> `timeline_read`.
6. `EXPORT_CHECKED` — Visual/audio result confirmed in a real Concat-exported MP4 verified by `verify_export.py`.
7. `USER_PERCEPTUAL_CONFIRMED` — Human reviewer confirmed playback, audio quality, and editorial intent.

## 2. Baseline Reference Matrix (Pinned Snapshot: Concat `v0.2.12`, Checked `2026-11-23`)

*Baseline entries below are `DOC_CLAIM` from official `jub0t/Concat` `docs/MCP.md` and release metadata (`v0.2.12`, published `2026-11-19`). Update your run's `CONCAT_CAPABILITY_MATRIX.json` with live results on each host.*

| Area | Documented MCP Tool(s) | Baseline Provenance | Notes / Known Caveats |
| --- | --- | --- | --- |
| Handshake / Mode | `concat_version` | `DOC_CLAIM` | Verify `mcp.mode == "headless"` & exact semver |
| Project Lifecycle | `project_list`, `project_create`, `project_open`, `project_save`, `project_close`, `project_set_video` | `DOC_CLAIM` | Edits stay in RAM until `project_save`; respects `concat.lock` |
| Inspection | `timeline_read`, `project_get` | `DOC_CLAIM` | Prefer `timeline_read` for compact loop checks |
| Media | `media_probe`, `media_import` | `DOC_CLAIM` | Subject to `$HOME` & `CONCAT_MCP_ROOTS` (`:` macOS / `;` Windows) |
| Timeline Edits | `track_add`, `clip_add`, `clips_add_sequence`, `clip_trim`, `clips_split`, `clips_move`, `clips_remove`, `clip_update`, `clip_speed`, `timeline_linkage` | `DOC_CLAIM` | Reconcile IDs via `timeline_read` before retrying timeouts |
| Framing / Picture | `clip_transform`, `clip_frame`, `timeline_background`, `clip_masks`, `mask_key_set`, `clip_stabilize` | `DOC_CLAIM` | Offsets/sizes documented as frame fractions |
| Keyframes / FX | `keyframe_set`, `keyframe_clear`, `effects_list`, `effect_layer_add`, `effect_key_set` | `DOC_CLAIM` | Keyframe time documented as clip fraction `0..1`; query `effects_list` dynamically |
| Titles / Captions | `title_add`, `title_style_words`, `title_clear_word_styles`, `captions_add` | `DOC_CLAIM` | Verify font availability & safe zones in preview + export |
| Atomic / Undo | `edit_apply`, `edit_undo`, `edit_redo` | `DOC_CLAIM` | Test undo granularity before scene batching |
| Templates | `template_list`, `template_instantiate` | `DOC_CLAIM` | Optional; never replace custom editorial craft |
| Visual Preview | `preview_frame` | `DOC_CLAIM` | Returns composited visual frame only (does NOT verify audio) |
| Export | `export_start`, `export_status`, `export_wait`, `export_cancel` | `DOC_CLAIM` | Sole authorized final MP4 producer; bound with timeout |
| Local TTS via MCP | *(Not documented in `docs/MCP.md`)* | `UNSUPPORTED_CURRENT_VERSION` (unless proven by live `tools/list`) | Fallback: audited local TTS WAV -> `media_import` |

## 3. Platform Notes for Capability Updates

- **macOS `arm64` / `x86_64`**: macOS 12+ base support; Intel macOS 12 lacks macOS 13.4+ ONNX runtime support for optional cutout/Enhance/Chatterbox models.
- **Windows `x86_64`**: Verify H.264/HEVC encoder path (Media Foundation / GPU vs LGPL OpenH264 fallback per `THIRD_PARTY_NOTICES.md`).
- **Version upgrades**: Always re-run Gate C1 after upgrading Concat and record the new version stamp rather than assuming backwards compatibility.
