# 11 — Source Inspiration, Official Provenance & License Audit Notes

All external repositories and documentation were inspected strictly as **untrusted reference material** (read-only metadata and conceptual study). No third-party renderer, paid dependency, or verbatim copyrighted code was bundled into this skill.

## 1. Core Execution Engine (Sole Native Editor & Exporter)

- **Project**: `jub0t/Concat` — `https://github.com/jub0t/Concat`
- **Verified Release Snapshot (`2026-11-23`)**: `v0.2.12` (published `2026-11-19`, beta)
- **Primary Docs**: `docs/MCP.md`, `LICENSING.md`, `THIRD_PARTY_NOTICES.md`, `https://concat.standalones.org/guides/install/`, `https://concat.standalones.org/guides/system-requirements/`
- **License**: **AGPL-3.0-or-later** (dual-licensed with a written commercial license option).
  - *Internal unmodified use* to produce and sell video files does not automatically trigger commercial engine licensing.
  - *Redistributing modified Concat* or offering a modified version as a network service triggers AGPL-3.0 obligations (or requires a commercial license).
  - *Codec patents*: Neither license grants H.264/HEVC/AAC patent licenses; Concat delegates to platform/OS codecs (VideoToolbox/AudioToolbox on macOS, Media Foundation/GPU on Windows) where available.
  - *Bundled FFmpeg*: LGPL shared libraries (`THIRD_PARTY_NOTICES.md`); optional AI models (Whisper, Robust Video Matting GPL-3.0, TTS models, fonts) each carry separate licenses — never collapse them under one label.

## 2. Selective Conceptual Planning Inspirations (No Engines Bundled)

| Repository | Verified License (Checked `2026-11-23`) | Principles Adapted (Original Implementation Only) | Explicitly Excluded |
| --- | --- | --- | --- |
| `browser-use/video-use` (`https://github.com/browser-use/video-use`) | **MIT License** | Compact read-only source analysis, editor-independent EDL reasoning, independent visual critic, boundary QA | Paid ElevenLabs Scribe dependency, FFmpeg final video renderer, video-use runtime |
| `FireRedTeam/FireRed-OpenStoryline` (`https://github.com/FireRedTeam/FireRed-OpenStoryline`) | **Apache License 2.0** | Storyline beat planning, structured asset gap analysis, style-aware visual casting, asset provenance tracking | Full FireRed application stack, heavy required cloud/model dependencies |
| `Melvynx/video-agent-skills` (`https://github.com/Melvynx/video-agent-skills`) | **MIT License** | Spoken-copy hook architecture, emotional beat pacing, B-roll visual indexing concepts | Default split-screen aesthetic, dense decorative karaoke captions |
| `remotion-dev/skills` (`https://github.com/remotion-dev/skills`) | **No SPDX `LICENSE` file found in repo** (Remotion core itself uses a dual free/company license) | General industry motion-design, typography legibility, and audio-craft discipline authored strictly in original prose | Zero verbatim text/code copied; zero Remotion renderer or Node/React rendering pipeline |

## 3. Licensing Hygiene Rules for Every Production Run

1. **Separate rights layers**: Track engine license, local AI model code license, model weights license, voice preset license, font license, and media asset license independently in `LICENSE_LEDGER.csv` and `COST_LEDGER.md`.
2. **No code/prompt copying from unlicensed repos**: Because `remotion-dev/skills` had no repository `LICENSE` file when audited on `2026-11-23`, zero content from that repository is copied or repackaged here.
3. **Antigravity Skills & Discovery Reference**: `https://antigravity.google/docs/skills`, `https://antigravity.google/docs/customization-discovery/`, and local built-in `agy-customizations` docs confirming `~/.gemini/config/skills/<name>/SKILL.md` and `~/.gemini/config/mcp_config.json`.
