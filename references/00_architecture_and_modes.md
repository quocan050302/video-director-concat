# 00 — Architecture, Modes & Decision Boundaries

## 1. Locked Single-Engine Architecture

```text
RAW SOURCE / USER BRIEF
  -> Platform Auto-Detect (Windows x64 / macOS arm64 / macOS x86_64)
  -> Antigravity Creative Director (video-director-concat)
  -> P0: Read-only source inventory, scene indexing, rights tagging
  -> P1-P2: Mode classification, creative brief, hooks/script, claim check
  -> P3: Storyboard, editor-independent frame-accurate EDL, MCP action plan
  -> P4-P5: Asset gap check, verified-rights media, local-first voice & audio cues
  -> P6: Concat native MCP editor (--mcp headless) — SOLE editor & exporter
  -> Critic Loop: preview_frame + timeline_read + bounded revisions (<=3)
  -> Save/Reopen check + Concat export_start/export_wait
  -> Post-Export QA: ffprobe, black/freeze vs EDL, audio signal, mobile scale
  -> Delivery: editable native Concat project + verified MP4 + QA + licenses + README
```

### Explicit Exclusions
- **No CapCut** in any new production workflow (existing CapCut installations, skills, projects, and plugins remain strictly untouched).
- **No secondary renderers**: Do not install or substitute FFmpeg, Remotion, FireRed full app, video-use renderer, Vedit, ShortGPT, MoneyPrinterTurbo, or OpenCut as final video renderers.
- **Planning principles only** are adapted from reference works (see [11_source_inspiration_license_notes.md](./11_source_inspiration_license_notes.md)).

## 2. Mode Classification & Storytelling Grammar

Classify each run from observable media truth and explicit user intent. Never hardcode one niche, duration, aspect ratio, voice, or caption rule.

1. **`product_ad` / `conversion_ad`**
   - Arc: Pain or desire -> clear offer -> genuine product proof -> concrete benefit -> trustworthy CTA.
   - Visuals: Show real, finished product evidence early. Never use AI-fabricated endorsements or competitor footage as proof.
   - Captions: **OFF by default**; use sparse, legible proof labels or CTA only when they clarify value.
2. **`software_demo`**
   - Arc: Outcome first -> key workflow steps -> verifiable result -> concise CTA.
   - Truthfulness: Local preview or staging screens must never be presented as live published results.
3. **`faceless_shorts` (history / science / mystery / storytelling)**
   - Arc: Intriguing first frame -> sharp hook -> curiosity escalation -> causal reveal -> honest payoff.
   - Integrity: Fact-check names, dates, and claims; clearly distinguish illustrative visuals from documentary footage.
4. **`product_review` / `affiliate`**
   - Arc: Honest experience -> verified strengths and limitations -> useful demonstrations -> transparent CTA.
   - No fabricated purchase proofs, results, or metrics.
5. **`tutorial` / `educational_explainer`**
   - Arc: Clear goal -> prerequisites -> readable step execution (targeted zoom on actual UI/cursor) -> outcome check.
   - Pacing: Hold long enough for viewers to read actions; avoid frantic cuts.
6. **`montage` (cooking / lifestyle / travel / aesthetic)**
   - Arc: Sensory rhythm -> visual motif -> craft progression -> hero reveal.
   - Audio: Preserve authentic natural audio and pacing; do not force synthetic narration or subtitles.
7. **`talking_head` / `podcast_clips`**
   - Arc: Speech-first beats -> dead-air trimming at sentence boundaries -> contextual B-roll -> clarity.
   - Captions: Apply when requested or beneficial for accessibility without covering faces/key graphics.
8. **`documentary_longform`**
   - Arc: Chapters with clear stakes, periodic rehooks, factual receipts, and breathing room.
   - Avoid applying short-form frantic pacing across multi-minute chapters.
9. **`existing_concat_project_repair`**
   - Arc: Independent audit of existing Concat project -> clone/backup -> root-cause defect list -> targeted MCP edits -> pre/post export comparison.

## 3. Minimal-Input Behavior

When the user supplies only a folder of raw clips:
- Derive visible facts from `SOURCE_INVENTORY.csv` and sampled contact sheets.
- Select the single most conservative, evidence-backed mode rather than asking 20 open questions.
- State all assumptions explicitly in the run header and `CREATIVE_BRIEF.md`.
- Omit unverifiable product offers, prices, discounts, or CTAs instead of inventing them.
- Always honor explicit user overrides for mode, aspect ratio, duration, voice, or captions.
