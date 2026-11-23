# 08 — Independent Critic, 3-Layer QA & No-Fake-PASS State Machine

Every output MUST pass three distinct QA layers before being called ready. Structural checks never prove visual quality; visual previews never prove export integrity; exit code 0 never proves creative value.

## 1. Three-Layer QA Architecture

### Layer 1 — Static & Structural QA (`PASS_STRUCTURAL_ONLY` at most)
- Original source hashes unchanged pre/post (`verify_source_hashes.py`).
- Every EDL shot has valid `OWNED`/`LICENSED`/`GENERATED` rights (`ANALYSIS_ONLY` and `UNKNOWN_RIGHTS` hard-blocked).
- `validate_edl.py` passes (bounds, rational frame grid, continuity, claim tags, mode/caption constraints).
- Isolated run folder, `LICENSE_LEDGER.csv`, `COST_LEDGER.md`, `RUN_README.md` exist.
- Concat `timeline_read` matches intended shot sequence, track layout, keyframe bounds, and duration.
- No unauthorized captions, no paid API calls, no unintended uploads.

### Layer 2 — Real Preview & Independent Editorial Critic (`CRITIC_NOTES.md`)
Inspect **actual Concat `preview_frame` PNGs** (never fabricated stills) at minimum checkpoints:
- Opening `0.0–2.0s` (immediate subject clarity, no blank/loading desktop).
- Pre- and post-cut frames (sampled across chapters for long-form).
- Keyframe motion start / mid / end (verify real movement where intended).
- Title overlays & final CTA/payoff at **50% mobile scale** and platform safe zones.

Score `0..5` per relevant dimension (weighted by mode, never claiming proven CTR/conversion prediction):
1. Opening scroll-stop / clarity (`0–2s`)
2. Message comprehension
3. Real visual / product evidence
4. Pacing & shot variety (novelty, no repetitive UI loops)
5. Typography, contrast & safe zones
6. Motion craft & transition motivation
7. Sound plan alignment
8. Audience payoff / honest CTA
9. Factual & rights integrity

Log defects in `CRITIC_NOTES.md` as `defect_id | timestamp | severity (P0/P1/P2) | frame_evidence | root_cause | proposed_mcp_edit | recheck_status`.
- **P0** (broken crop, blank frame, wrong claim, unreadable text, missing proof, rights error) -> mandatory fix & re-preview.
- Cap creative revision loops at **3 bounded iterations**. If visual inspection is unavailable -> `PREVIEW_VISUAL_PENDING`.

### Layer 3 — Post-Export Real MP4 QA (`verify_export.py`: Two-Axis & Phase-Locked)
Strictly separate `CODE_QUALITY` from `RUNTIME`, and standalone diagnostics from phase-locked release checks:
- **`--qa-level technical`** (standalone media diagnostic): Runs `ffprobe`, full `ffmpeg` decode check, spec check, `blackdetect` + `freezedetect` (with EOF trailing freeze closure and strict ffmpeg exit checks), and audio signal measurements (`volumedetect`, `ebur128` LUFS/true peak, `silencedetect` including EOF silence against planned cues). Returns **`PASS_TECHNICAL_ONLY`** at most — NEVER certifies Concat origin or release readiness.
- **`--qa-level release --gate-phase C1|C2|C4 --release-policy technical-smoke|full-creative`**:
  1. **`LIVE_MCP_EXPORT_EVIDENCE`** required for `live_concat_verified=true` (`UNIT_SIMULATED_PROVENANCE` caps at `PASS_SCHEMA_CONSISTENCY_UNIT_ONLY`). Verifies `concat_binary_sha256`, complete `tool_trace`, matched `export_start.job_id == export_wait.job_id`, plausible timestamp order, `timeline_fingerprint_before_save == timeline_fingerprint_after_reopen`, non-symlink project/export roots, and exact MP4 `sha256`.
  2. **Non-empty `PREVIEW_MANIFEST.json`** with `origin: "CONCAT_MCP_PREVIEW_FRAME"` correlated to `preview_frame` `tool_call_id`s (rejects frames extracted from MP4), verified for dimensions, SHA-256, SSIM, and PSNR.
  3. **Phase-locked policy**: `technical-smoke` is strictly limited to `C1`, sets `technical_e2e_gate_pass=true` while keeping `creative_release_gate_pass=false` and `release_gate_pass=false` (`C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING`). Combining `technical-smoke` with `C2` or `C4` hard-fails (`INVALID_RELEASE_POLICY_FOR_PHASE`).
  4. **`OWNER_HUMAN` Perceptual Audio Gate**: Rejects agent/bot reviewer records; requires owner playback confirmation + auditory checklist + matching MP4 `sha256` for `PASS_END_TO_END_EXPORT_QA`.
- Confirm native Concat project reopens cleanly and remains editable alongside the MP4.

## 2. Formal Status State Machine (No Status Inflation)

| State | Mandatory Evidence Required |
| --- | --- |
| `SKILL_FILES_CREATED` | Full skill directory tree written |
| `SKILL_STATIC_VALIDATED` | `check_skill_package.py` + `pytest` all pass; `MANIFEST.json` matches |
| `SKILL_INSTALLED_GLOBAL` | Installed to discovered global skill path; post-copy SHA-256 verified |
| `SKILL_DISCOVERY_VERIFIED` | Fresh Antigravity session discovers exactly ONE `video-director-concat` skill (else `ACTIVATION_PENDING_NEW_SESSION`) |
| `MCP_CONNECTED` | Live `initialize` + `ping` + `tools/list` + `concat_version` (`mode=headless`) |
| `C1_NATIVE_PROJECT_CREATED` | Native Concat project ID + path + verified `timeline_read` |
| `C1_PREVIEW_VERIFIED` | Real Concat `preview_frame` PNGs saved and visually inspected |
| `C1_REOPEN_VERIFIED` | `project_save` -> `project_close` -> `project_open` -> semantic timeline match |
| `C1_EXPORT_VERIFIED` | Concat `export_start` + `export_wait` succeeded + MP4 exists + SHA-256 |
| `C1_MP4_QA_PASS` | `verify_export.py` passes technical/visual/audio-signal checks |
| `C2_CREATIVE_DRAFT_CREATED` | New owned footage brief + EDL + native Concat edit |
| `C2_CREATIVE_PREVIEW_VERIFIED` | Independent critic inspection + bounded revision pass |
| `C2_FINAL_EXPORTED` | Real Concat MP4 exported for creative deliverable |
| `C2_FINAL_QA_PASS` | Full Layer 1–3 QA + rights/claims audit pass |
| `READY_FOR_BATCH_PRODUCTION` | C1 + C2 + C4 bounded stress/repeat/resource tests pass |

Allowed per-gate test codes: `PASS`, `FAIL`, `PENDING`, `BLOCKED_ENV`, `PENDING_OWNER_SECURITY_APPROVAL`, `UNSUPPORTED_CURRENT_VERSION`, `SKIPPED_NOT_APPLICABLE`, `PASS_STRUCTURAL_ONLY`, `PERCEPTUAL_AUDIO_PENDING`, `PREVIEW_VISUAL_PENDING`.

**Anti-Gaming Rule**: Never delete an artistic fade-to-black just to appease `blackdetect`, never inject loud SFX to inflate RMS, never split 5 strong shots into 30 choppy clips to inflate pacing metrics.
