# 12 — KH-01: Video-Use Planning & Creative Fidelity Standard

**Canonical Label**: `KH-01 — Video-Use Planning & Creative Fidelity`

KH-01 hardens creative editorial fidelity across **all niches, formats, aspect ratios, languages, and production modes** (`product_ad`, `software_demo`, `faceless_shorts`, `product_review`, `tutorial`, `montage`, `talking_head`, `documentary_longform`, `existing_concat_project_repair`). Never hardcode any single product, duration, aspect ratio, narration language, or caption policy inside this standard — those belong strictly in each run's `CREATIVE_BRIEF.md`.

> **Conceptual Provenance & Engine Boundary**: KH-01 adapts editor-independent planning and critic-loop principles from [`browser-use/video-use`](https://github.com/browser-use/video-use) (MIT License) using original code and specifications. It does **not** install `video-use`, ElevenLabs Scribe, or an FFmpeg video renderer. **Concat MCP (`--mcp headless`)** remains the sole native project editor and final MP4 exporter.

---

## 1. Three Cross-Cutting KH-01 Stages

### `KH-01/P0` — Independent Source Audit, Role Lock & Reference-Only Style DNA
1. **Source Pack & Role Lock (`SOURCE_ROLE_AUDIT.json`, `SOURCE_ZIP_PROVENANCE.json`)**:
   - Verify expected input package contents, sizes, and SHA-256 hashes before extraction (reject zip-slip, symlinks, archive bombs, case collisions, and corrupt streams).
   - Never silently fall back to a partial/smaller source archive when required source roles are missing; stop at a clean preflight blocker and log exact missing paths.
   - Audit candidate owned/licensed media **separately** from `ANALYSIS_ONLY` references and `GENERATED` audio (e.g., never inflate media coverage counts by substituting generated WAVs for missing footage).
2. **Semantic Scene Index (`SCENE_INDEX.json`)**:
   - Extract bounded contact sheets and fine strips around real action, subject gestures, UI outcomes, and transitions.
   - Index verified `in/out` timestamps with subject clarity, resolution/crop tolerance, VFR warnings, motion quality, rights tag, and confidence.
   - Explicitly evaluate authentic human/real-world viewpoints (when provided): use them purposefully where legible, or log an evidence-backed `SOURCE_FIDELITY_GAP` exception rather than silently omitting them.
3. **Reference-Only Style Grammar (`COMPETITOR_STYLE_DNA.md`, `REFERENCE_TO_ORIGINAL_ADAPTATION.csv`)**:
   - Tag competitor/reference clips strictly `ANALYSIS_ONLY`. **Hard-blocked** from `EDL.json`, Concat `media_import`, audio tracks, stills, and overlays.
   - Measure transferable craft grammar only: opening `0–2s` hook mechanism, cut timestamps/rhythm, framing fill & subject hierarchy, overlay restraint, camera moves, and sound dynamics.
   - Never copy competitor pixels, audio, trademarks, scripts, or shot-for-shot compositions.

### `KH-01/P3` — Editor-Independent EDL Reasoning, Creative Plan Gate & Early Hook Preview
1. **Viewer-Driven Storyboard & Frame-Accurate EDL (`STORYBOARD.csv`, `SHOT_LIST.md`, `EDL.json`, `CONCAT_MCP_ACTION_PLAN.json`)**:
   - Build story beats for viewer intent rather than raw filename order.
   - Align shot durations with verified voiceover/rhythm timing, rational FPS (`30/1`, `24000/1001`, `60/1`, etc.), and explicit framing/crop plans for aspect conversions (avoid unintended black bars hiding tiny subjects).
   - Enforce `voice_policy`: when `voice_policy == "REQUIRED"`, the EDL MUST include an actual planned voiceover/narration track (`MISSING_REQUIRED_VO_TRACK` otherwise).
   - Enforce `caption_policy`: when `caption_policy == "OFF"`, reject continuous subtitles/karaoke while permitting sparse intentional proof/CTA overlays per brief.
2. **Creative Plan Gate (`CREATIVE_PLAN_GATE.json`) — Must PASS Before Full Timeline Build**:
   - All expected source roles audited and `ANALYSIS_ONLY` proven absent from EDL.
   - Reference Style DNA documented (whenever a reference clip is supplied).
   - Opening `0–2s` immediately serves the buyer/viewer hook (not idle loading/tooling screens unless the brief explicitly requires it).
   - Every commercial claim and CTA is grounded in verified product/source truth (`OFFER_VERIFIED.md` / `SOURCE_TRUTH.md`).
   - Audio/voice feasibility, license ledger, and framing contrast plan confirmed.
3. **Early First-5s Hook Preview Gate (`KH01_HOOK_PREVIEW_GATE.json`)**:
   - Assemble the opening `3–5s` directly in Concat MCP first and capture real `preview_frame` PNGs (`0s`, `0.5s`, `1.5s`, `2.5s`, `4s` clamped to clip length).
   - Visually inspect actual saved PNGs for hook clarity, framing fill, subject scale, and overlay legibility BEFORE editing the full timeline. Revise structure immediately if it fails.

### `KH-01/QA` — Three Independent Axes & Dual Human Owner Gates
Never conflate structural JSON validation, `ffprobe` decode, or preview SSIM with creative quality or commercial readiness. Report **two independent top-level statuses** on every creative run:

```text
TECHNICAL_EXPORT_STATUS=PASS|FAIL|BLOCKED
CREATIVE_PRODUCTION_STATUS=DRAFT|PENDING_OWNER_REVIEW|REJECTED|PASS
```

1. **Axis A — Technical QA (`verify_export.py --qa-level release --gate-phase C2 --release-policy full-creative`)**:
   - On-disk source integrity pre/post (`verify_source_hashes.py`), `LIVE_OBSERVED_WITH_RAW_TRANSCRIPT` Concat MCP provenance, save/close/reopen semantic match, full H.264/AAC decode, black/freeze check vs EDL, real `CONCAT_MCP_PREVIEW_FRAME` SSIM/PSNR match, and `PASS_AUDIO_SIGNAL` across all mandatory planned audio tracks.
2. **Axis B — Independent Creative Visual Critic (`CRITIC_NOTES.md`, bounded `<=3` revisions)**:
   - Inspect real preview PNGs and exported frames at mobile/target viewing scale across 10 editorial heuristics (`0..5`, grounded in actual frame evidence; heuristic guide only — **never** an automated numeric pass rule or conversion/retention guarantee):
     1. Opening `0–2s` visual hook
     2. Audience problem/value clarity
     3. Authentic product/subject proof
     4. Shot variety & purposeful human/real-world viewpoints
     5. Canvas composition & UI/subject legibility
     6. Camera motion, framing & transition craft
     7. Natural narration & balanced mix plan
     8. Credible, evidence-backed CTA & claims
     9. Visual style cohesion
     10. Rights hygiene & absence of `ANALYSIS_ONLY` content
   - **Hard P0 defects** (must fix before proceeding): `ANALYSIS_ONLY` content present, wrong/partial input archive used, opening violates brief hook, empty black bars dominating canvas with unreadable UI, unverified claims/licenses, missing mandatory VO, continuous caption clutter when `caption_policy=OFF`.
3. **Axis C — Dual Human Perceptual Gates (`OWNER_VISUAL_GATE.md`, `OWNER_AUDIO_GATE.md`)**:
   - **`OWNER_VISUAL_APPROVAL`**: Recorded strictly by `OWNER_HUMAN` (`OWNER_INTERACTION_RECORDED`, `viewing_confirmed: true`, exact `mp4_sha256`, `reviewed_at >= exported_at`) confirming visual appeal, composition, legibility, and brief alignment.
   - **`OWNER_AUDIO_APPROVAL`**: Recorded strictly by `OWNER_HUMAN` (`OWNER_INTERACTION_RECORDED`, `playback_confirmed: true`, exact `mp4_sha256`, `reviewed_at >= exported_at`, content-aware auditory checklist) confirming natural VO, ducking, SFX balance, and pronunciation.
   - **Fail-Closed Rule**:
     - Audio approval alone WITHOUT visual approval on `C2`/`C4` `full-creative` -> `PENDING_OWNER_VISUAL_APPROVAL` (`creative_release_gate_pass=false`, `production_release_pass=false`).
     - Explicit owner rejection on EITHER visual or audio -> **`CREATIVE_REJECTED`** (`creative_production_status="REJECTED"`), overriding any passing technical checks or unit tests.
     - Agents may **never** fabricate or self-sign either owner approval.

---

## 2. Standard Regression Checklist (`T01–T12`)

| ID | Gate Verified |
| --- | --- |
| `T01` | Partial/wrong input pack fails required-source-count preflight |
| `T02` | Full multi-source pack separates owned/licensed inputs from `ANALYSIS_ONLY` reference and `GENERATED` audio |
| `T03` | `ANALYSIS_ONLY` source in EDL shots, audio, or overlays hard-fails validation |
| `T04` | Authentic real-world/hand viewpoint included in EDL or requires explicit evidenced exception |
| `T05` | Unverified licenses or unverified/removed commercial claims hard-fail release validation |
| `T06` | Missing VO track when `voice_policy=REQUIRED` hard-fails creative validation |
| `T07` | Landscape-in-portrait letterbox/black-bar framing risk emits objective warning + critic gate |
| `T08` | Owner audio approval alone without `OWNER_VISUAL_APPROVAL` never grants `C2` creative release PASS |
| `T09` | Owner creative rejection emits `CREATIVE_REJECTED` even when technical QA & tests pass |
| `T10` | `C2` release EDL validation requires real per-file on-disk `verify_source_hashes.py` SHA-256 report |
| `T11` | Source probing manifest & hashes remain deterministic across `1`/`2`/`4` workers |
| `T12` | Live runtime evidence (not CI simulation) verifies native Concat save/reopen & real MCP export trace |
