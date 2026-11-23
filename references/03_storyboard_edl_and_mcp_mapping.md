# 03 — Storyboard, Frame-Accurate EDL & Concat MCP Action Plan (Phase P3)

Keep creative editorial planning strictly decoupled from editor-specific RPC calls:

1. **`STORYBOARD.csv`** — Human-readable shot-by-shot plan (visuals, framing, motion, audio, titles, proof).
2. **`EDL.json`** — Editor-independent, machine-validated intermediate representation (IR) on a rational frame grid.
3. **`CONCAT_MCP_ACTION_PLAN.json`** — Deterministic mapping from validated EDL intents to **actually discovered** Concat MCP tools from `tools/list`.

## 1. Frame-Accurate EDL Contract (`release` vs `draft`)

All shot timing, rights, and claim citations are validated by `python3 scripts/validate_edl.py` BEFORE any Concat edit tool is called:
- **Fail-Closed `release` mode (default, `--validation-mode release --run-dir <dir>`)**:
  - Rejects duplicate `source_id` in `SOURCE_INVENTORY.csv` and duplicate `asset_id` in `LICENSE_LEDGER.csv` (never silent last-wins).
  - Requires an independently probed `SOURCE_INVENTORY.csv`/`.json` (empty/missing inventory -> `MISSING_SOURCE_INVENTORY`).
  - Every `source_id` in `shots`, `audio_tracks`, AND media `overlays` MUST exist in inventory with `probe_status == "OK"`, a valid 64-hex `sha256`, and a cross-platform safe `relative_label` (rejects both `/` and `\` traversal, drive prefixes, and NUL bytes).
  - Inventory `rights_tag` is authoritative — EDL `source_rights` is a consistency check only, never self-certification.
  - `ANALYSIS_ONLY` and `UNKNOWN_RIGHTS` are hard-blocked across video, audio, and overlays.
  - `LICENSED` requires `LICENSE_LEDGER.csv` entry with `decision=APPROVED`, `commercial_use_allowed=YES`, and an archived `license_evidence_path` verified on disk (`license_url` alone is insufficient).
  - `GENERATED` requires separate code and weights/model/voice licenses plus archived `license_evidence_path` in `LICENSE_LEDGER.csv`.
  - Claims marked `VERIFIED_WITH_EVIDENCE` require `--run-dir` (or verified evidence bundle), non-empty resolvable evidence file with verified `#fragment` anchor content, valid `source_id` membership if supplied, never pointing to `ANALYSIS_ONLY` sources, and ISO `checked_at` + local `evidence_archive_path` for `http(s)` URLs. Structural check is distinct from human factual review.
  - For C2/final gates, pass `--source-integrity <verify_source_hashes.json> --require-source-integrity` to confirm on-disk `PASS_SOURCE_INTEGRITY` separately from structural EDL eligibility.
  - Returns `PASS_EDL_VALID_FOR_RELEASE` only when every release check passes.
- **Draft mode (`--validation-mode draft`)**: Permits planning drafts without full inventory/ledger while still enforcing frame grid, finite numerics, and blocking `ANALYSIS_ONLY` / `UNKNOWN_RIGHTS` / `UNKNOWN_REMOVE`. Returns `PASS_EDL_DRAFT_ONLY` (never release green).
- **Rational FPS & Layered Tracks**: Declare `"timeline_fps": "30/1"` (or `"24000/1001"`, `"30000/1001"`, `"60/1"`). Reject `NaN`/`Infinity`/bools/invalid speeds. `V1` must be continuous without unintended gaps/overlaps; `V2+` overlay shots and still-image shots are validated within `[0, V1_end]`.
- **Aspect safety**: Flag landscape-to-portrait (`16:9` -> `9:16`) shots missing explicit `framing_mode` (`framed`, `blur_bg`, `crop_tracked`, `letterbox_intentional`) so UI/product details are never accidentally sliced off.

See [templates/EDL.example.json](../templates/EDL.example.json) for the canonical schema.

## 2. Mapping EDL to `CONCAT_MCP_ACTION_PLAN.json`

Every step in the action plan MUST record:
- `step_id`, `phase`, `operation_intent`
- `exposed_mcp_tool` (verified against live `CONCAT_CAPABILITY_MATRIX.json` — never invented)
- `source_ids`
- `precondition` and `expected_postcondition`
- `rollback_strategy` (`edit_undo`, `project_close` without save, or revert to checkpoint)
- `evidence_path` (e.g., `timeline_read` snapshot or `preview_frame` PNG)
- `status` (`PLANNED` before execution; updated only after verified tool response)

### Transaction Granularity & Timing Semantics
- Group edits into small, verifiable transactions (e.g., setup -> media import -> V1 rough cut -> framing/keyframes -> titles -> audio layers -> save).
- Only batch via `edit_apply` after verifying its undo/atomicity behavior on the current Concat version; batch at most one logical scene at a time.
- **Keyframes**: Per Concat `docs/MCP.md`, timeline times are in **seconds**, keyframe positions are **fractions `0.0..1.0` of the clip**, and sizes/offsets are **fractions of the frame** (not CapCut microseconds!). Always verify exact parameter names and ranges against live `tools/list` JSON schemas.
- If a desired creative intent has no exposed MCP tool, mark it `UNSUPPORTED_CURRENT_VERSION`, log it in `MCP_LIMITATION.md`, and choose a clean native fallback (e.g., clean hard cut instead of unexposed wipe).
