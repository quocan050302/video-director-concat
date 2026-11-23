# 06 — Motion Craft, Effects, Composition & Typography

Motion, transitions, and typography exist strictly to direct viewer attention and clarify proof — never to decorate weak storytelling or showcase tool inventories.

## 1. Camera & Keyframe Discipline

- **Purposeful motion only**: Every zoom or pan must have a clear visual target (product detail, cursor action, facial expression, chart inflection). Static shots are valid and often superior when the footage already contains strong subject motion.
- **Anti-robotic rules**:
  - Do not apply constant-velocity zoom-in on every single clip.
  - Avoid artificial shake/jitter unless motivated by diegetic impact.
  - Only apply easing/curves that are genuinely exposed by Concat's `keyframe_set` schema and visually verified across rendered frames.
- **Screen recordings / tutorials**: Zoom deliberately into the exact button, input, or result text; hold long enough to read; pull back to restore spatial context before moving to the next step.
- **Stills & photo montages**: Gentle framing shifts only — never claim fake 3D parallax/depth unless supported by verified native features.

## 2. Aspect Ratio Mapping & Framing

- Never hardcode 9:16 or 16:9; derive output canvas from user intent and platform.
- When placing **16:9 landscape footage into a 9:16 portrait frame**:
  - Check whether center-crop cuts off product proof, UI controls, or speaker faces.
  - If full-width context matters (e.g., software UI or product layout), use `framed` or `blur_bg` (`timeline_background` / scaled backdrop) instead of destructive blind cropping.
  - Avoid unintended empty black letterbox bars unless explicitly declared as a stylistic choice in `CREATIVE_BRIEF.md`.

## 3. Native Effects & Transitions

- Query `effects_list` at runtime and select ONLY genuine returned effect/transition IDs. Never invent effect IDs or assume GUI transitions exist in MCP.
- Prefer clean, motivated **hard cuts** over ornamental wipes/spins. Use dissolves or tested native transitions only to bridge time, space, or mood shifts.
- Verify every applied effect in BOTH `preview_frame` AND the final exported MP4 (some beta effects can preview differently from export).

## 4. Typography & Platform Safe Zones

- **Safe zones**:
  - Portrait (`9:16` Shorts/Reels/TikTok): keep essential text/CTAs roughly inside normalized `x=[0.08..0.92]`, `y=[0.12..0.78]` (avoiding top status bar and bottom caption/UI/right action buttons).
  - Landscape (`16:9`): keep within 5–10% title-safe margins.
- **Legibility**:
  - Verify contrast against local background frames at **50% mobile scale**, not just full desktop zoom.
  - Add subtle backing plate, stroke, or drop shadow only where needed for legibility — never cover product evidence, faces, or tutorial cursors.
  - Hold titles long enough for comfortable reading (~0.35s per word minimum, plus onset/offset margin).
- **Caption policy**:
  - `product_ad`: **Captions OFF by default**; sparse proof labels / CTA only when justified.
  - `tutorial` / `talking_head` / accessibility requests: enabled per mode or user request, checking UI occlusion.
- **Font licensing**: Use verified system or explicitly licensed bundled fonts; log non-system fonts in `LICENSE_LEDGER.csv`.
