# 04 — Asset Gaps, Stock/Music/SFX & Licensing Governance (Phase P4)

External assets exist strictly to close real narrative or audio gaps — never to pad a video with generic stock clips unrelated to the user's real subject.

## 1. Asset Gap Analysis (`ASSET_GAPS.md`)

Before searching online or generating anything, document every gap:
- `gap_id`, `beat_id` / `shot_id`, missing visual or audio function
- Why existing owned footage cannot cover it
- Exact targeted search queries (bounded — never bulk-scrape catalogs)
- Acceptable substitutes if online search is unavailable (`ASSET_PENDING` + adapt edit to owned footage)
- Technical spec (resolution, aspect, FPS, sample rate) and commercial license requirement

## 2. Commercial Rights Verification (`LICENSE_LEDGER.csv`)

Maintain `LICENSE_LEDGER.csv` for EVERY run (if zero external assets are used, keep header row and record `NO_EXTERNAL_ASSETS` in `RUN_README.md`).

For each external video, image, music track, SFX, font, or AI-generated asset, record:
- `asset_id`, `asset_type`, `local_staging_path`, `sha256`
- `source_url`, `creator`, `platform_asset_id`, `downloaded_at`
- `license_name`, `license_url`, `license_evidence_path` (archived text/screenshot at acquisition time)
- `commercial_use_allowed` (`YES`/`NO`/`CONDITIONAL`), `attribution_required`, `redistribution_restrictions`, `model_or_property_release_notes`
- `decision` (`APPROVED`, `REJECTED`, `ANALYSIS_ONLY`, `PENDING`)

### Strict Prohibitions
- Never rip audio, music, or clips from TikTok, YouTube, Instagram, films, TV, or competitor ads.
- Never assume "free download" or "royalty-free" equals unrestricted commercial rights — inspect the exact license page for each asset.
- Never strip stock watermarks. (Cropping an OS menu bar on user-owned screen recordings is allowed only if it hides no truthful context.)
- Separate software code licenses, pretrained AI model weight licenses, voice preset licenses, font licenses, and codec patent notices — never collapse them into a single label.

## 3. Zero-Paid-API Cost Ledger (`COST_LEDGER.md`)

Log every component in `COST_LEDGER.md` (and `COST_LEDGER_MACOS.md` when running on macOS):
- Component name, license, download bytes, installed state, cloud upload behavior (`LOCAL_ONLY` vs network download vs upload), hardware impact, direct monetary cost (`$0` vs paid), and owner approval status.
- **Important honesty rule**: Concat being AGPL-3.0-or-later and free to run locally does NOT mean Antigravity agent tokens, electricity, SSD wear, or third-party media licenses are universally `$0`. Document account quota and hardware costs truthfully.
- **Concat AGPL-3.0-or-later note**: Using unmodified Concat locally to produce and sell videos does not automatically require purchasing a commercial license. Modifying Concat and distributing it or hosting it as a network service triggers AGPL / commercial licensing review — stop and audit first.
- If any paid stock, paid TTS/STT, or paid cloud API is ever requested or needed, stop at `STOP_FOR_COST_APPROVAL` with an explicit cost estimate and a free local alternative.
