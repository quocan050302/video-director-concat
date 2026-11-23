# 03 — Storyboard, Frame-Accurate EDL & Concat MCP Action Plan (Phase P3)

Keep creative editorial planning strictly decoupled from editor-specific RPC calls:

1. **`STORYBOARD.csv`** — Human-readable shot-by-shot plan (visuals, framing, motion, audio, titles, proof).
2. **`EDL.json`** — Editor-independent, machine-validated intermediate representation (IR) on a rational frame grid.
3. **`CONCAT_MCP_ACTION_PLAN.json`** — Deterministic mapping from validated EDL intents to **actually discovered** Concat MCP tools from `tools/list`.

## 1. Frame-Accurate EDL Contract

All shot timing is validated by `python3 scripts/validate_edl.py` BEFORE any Concat edit tool is called:
- **Rational FPS**: Declare `"timeline_fps": "30/1"` (or `"24000/1001"`, `"60/1"`, etc.). Use integer `output_in_frame` and `output_out_frame` on the timeline; convert seconds cleanly on the rational grid.
- **Source bounds**: Require `0 <= source_in_s < source_out_s <= source_duration_s`. Flag speed/retime mismatches where `(source_out_s - source_in_s) / speed` diverges from `(output_out_frame - output_in_frame) / fps`.
- **Continuity**: Detect unintended timeline gaps, accidental visual track overlaps (unless explicitly tagged as a transition/dissolve overlap), and duplicate `shot_id`s.
- **Rights gate**: Hard-reject any shot referencing `ANALYSIS_ONLY` or `UNKNOWN_RIGHTS` sources, or external `LICENSED` assets missing from `LICENSE_LEDGER.csv`.
- **Claim & mode gate**: Reject shots bound to `UNKNOWN_REMOVE` claims; flag unauthorized captions when `caption_policy == "OFF"`.
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
