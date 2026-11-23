# Creative Brief

- **Run ID**: `<YYYYMMDD_HHMMSS_slug>`
- **Platform**: `<Darwin/arm64 | Darwin/x86_64 | Windows/x86_64>`
- **Primary Mode**: `<product_ad | software_demo | faceless_shorts | product_review | tutorial | montage | talking_head | documentary_longform | existing_concat_project_repair>`
- **Secondary Tags**: `<optional>`
- **Style Profile**: `<concise visual/editorial style>`

## 1. Objective & Audience
- **Goal**: `<what viewer should understand or do>`
- **Target Viewer**: `<persona/context>`
- **Platform & Delivery Format**: `<aspect ratio, width x height, rational FPS, target duration range>`
- **Safe Zones**: `<normalized x_min..x_max, y_min..y_max>`

## 2. Core Narrative & Truth Basis
- **Core Tension / Value Proposition**: `<one clear sentence>`
- **Verified Visual Proof Available**: `<reference source_ids from SOURCE_INVENTORY.csv>`
- **Assumptions Disclosed**: `<what was inferred because user input was minimal>`
- **Omitted / Unverified Claims**: `<explicitly dropped claims>`

## 3. Visual, Typography & Motion Identity
- **Framing / Aspect Strategy**: `<native | framed | blur_bg | crop_tracked>`
- **Camera Motion Stance**: `<static default + targeted zooms where justified>`
- **Transition Grammar**: `<clean hard cuts / motivated dissolves>`
- **Typography & Palette**: `<font + license status, contrast strategy>`
- **Captions Policy**: `<OFF (default for product_ad) | ON (reason & occlusion check)>`

## 4. Audio & Voice Stance
- **Voiceover**: `<NONE | local Kokoro English-US | user-recorded | other>`
- **BGM & SFX Direction**: `<mood, ducking approach, sparse motifs>`

## 5. Measurable Acceptance Criteria
1. Opening `0–2s` establishes subject immediately with zero blank/loading frames.
2. All claims match `VERIFIED_WITH_EVIDENCE` sources; zero `ANALYSIS_ONLY` assets in final cut.
3. Text/CTA legible at 50% mobile scale within platform safe zones.
4. Native Concat project saves, reopens cleanly, and exports verified MP4 passing `verify_export.py`.

## 6. Negative Constraints (What to Avoid)
- `<e.g., No decorative karaoke captions covering product proof, no robotic constant zoom, no unverified discount claims>`
