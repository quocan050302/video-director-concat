# 02 — Creative Direction, Hooks, Script & Factual Integrity (Phases P1–P2)

Think as an experienced human editor and creative director — never as a generic short-form template generator.

## 1. Creative Brief (`CREATIVE_BRIEF.md`)

Every creative production run produces `CREATIVE_BRIEF.md` containing:
- **Intent**: Viewer persona, target platform, desired viewer action, core tension or value proposition.
- **Mode & Format**: Selected `mode`, aspect ratio, resolution, FPS, target duration range, platform safe zones.
- **Visual Language**: Typography hierarchy, contrast strategy, framing/crop approach (e.g., blurred/solid canvas vs crop for 16:9->9:16), camera motion discipline, transition motivation.
- **Audio & Captions Stance**: Whether VO is needed (optional!), voice timbre/pace for the niche, BGM/SFX role, and explicit caption policy (`OFF` by default for clean `product_ad`).
- **Evidence-Backed Claims**: Every claim linked to `SOURCE_TRUTH.md` or verified URL; omit unverified offers, prices, or performance stats.
- **Negative Constraints**: Explicitly list what would make this video feel robotic, generic, cluttered, or misleading.

*Note*: For pure engine smoke tests (Gate C1), skip elaborate marketing copy and hook ideation to save tokens and keep technical validation clean.

## 2. Hook Ideation (`HOOK_CANDIDATES.md`)

Only generate hook candidates when narrative/marketing structure benefits from them (skip artificial hooks for serene montages or technical smoke runs):
- Draft **up to 3 genuinely distinct angles** (different conceptual tension, not word swaps).
- Score each candidate `0..5` on: (1) attention contrast, (2) visual match to real footage, (3) immediate clarity, (4) factual honesty, (5) audience relevance, (6) curiosity-to-payoff alignment.
- **Tri-channel complementarity**: First visual frame shows something visually intriguing, opening voice starts the narrative beat, and optional on-screen title creates curiosity — never repeat the exact same sentence across title, voice, and caption simultaneously.
- Reject clickbait lies, ALL-CAPS yelling, emoji spam, and unverifiable promises.

## 3. Script & Spoken Copy (`SCRIPT_AND_VO.md`)

- Tag every beat with `beat_id`, `scene_purpose`, `viewer_state`, `visual_proof_source_id`, and estimated spoken duration.
- Cut filler sentences that add no proof, emotion, turn, or payoff.
- **Realistic speaking pace**: Budget natural words-per-minute (typically 130–165 WPM for English-US depending on voice/mode) plus semantic pauses (0.25–0.6s at turns). Never cram 120 words into 20 seconds and artificially speed up the voice.
- **Mode-specific honesty**:
  - *Product ads*: Show the actual finished product clearly; tie every benefit to visible proof.
  - *History / science*: Fact-check names, dates, and causality; never present illustrative graphics as archival proof.
  - *Tutorials*: Match every spoken step to visible cursor/UI action and hold until the outcome is legible.
  - *Long-form*: Structure chapters with clear stakes, callbacks, and visual breathing room.

## 4. Claim Audit Labels

Tag every statement in `SCRIPT_AND_VO.md` and on-screen titles:
- `VERIFIED_WITH_EVIDENCE`: Supported by visible owned source or verified primary documentation.
- `PLAUSIBLE_NOT_ADVERTISABLE`: Reasonable context, not a hard commercial guarantee (rephrase softly or omit in ads).
- `UNKNOWN_REMOVE`: Unverified claim — must be deleted before EDL lock.
