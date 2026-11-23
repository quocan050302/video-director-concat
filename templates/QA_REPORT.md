# Quality Assurance Report

- **Run ID**: `<YYYYMMDD_HHMMSS_slug>`
- **Platform**: `<os_version / arch>`
- **Concat Binary & Version**: `<verified path, binary_source & version, or NOT_INSTALLED>`
- **QA Level Executed**: `<technical | release>`
- **Overall Verified State**: `<exact state from formal state machine — NEVER inflate PASS_TECHNICAL_ONLY into PASS_END_TO_END_EXPORT_QA>`

## Gate Status Table

| Gate | Status | Evidence Path | Notes / Exact Blocker |
| --- | --- | --- | --- |
| M0 / C0 Environment & Disk Guard | `<PASS / BLOCKED_LOW_DISK / BLOCKED_ENV>` | `ENV_MATRIX.json` | `<decoupled OS, disk, binary, QA tools>` |
| C0 MCP Connected (`--mcp headless`) | `<PASS / BLOCKED_ENV / FAIL>` | `CONCAT_CAPABILITY_MATRIX.json` | `<live initialize + tools/list + concat_version>` |
| Layer 1 Release EDL & Rights Gate (`--validation-mode release`) | `<PASS_EDL_VALID_FOR_RELEASE / PASS_EDL_DRAFT_ONLY / FAIL>` | `SOURCE_INVENTORY.csv`, `EDL.json`, `LICENSE_LEDGER.csv` | `<inventory-authoritative rights, GENERATED provenance, claim evidence>` |
| Layer 2 Preview & Critic | `<PASS / PREVIEW_VISUAL_PENDING / BLOCKED_ENV>` | `PREVIEW_EVIDENCE/`, `PREVIEW_MANIFEST.json`, `CRITIC_NOTES.md` | `<calibrated SSIM + PSNR + dimensions>` |
| Native Project Save / Reopen | `<PASS / BLOCKED_ENV / FAIL>` | `MCP_EXPORT_EVIDENCE.json` | `<semantic timeline fingerprint match>` |
| Layer 3 Concat MP4 Export & Provenance (`--qa-level release`) | `<PASS_END_TO_END_EXPORT_QA / C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING / PENDING_PERCEPTUAL_AUDIO / PASS_TECHNICAL_ONLY / BLOCKED_ENV / FAIL>` | `POST_EXPORT_QA.json`, `MCP_EXPORT_EVIDENCE.json` | `<full ffmpeg decode + EOF freeze + SHA256 match>` |
| Audio Signal QA (`PASS_AUDIO_SIGNAL`) | `<PASS / BLOCKED_ENV / FAIL>` | `POST_EXPORT_QA.json` | `<volumedetect + ebur128 LUFS/true peak + silencedetect>` |
| Audio Perceptual QA (`PASS_AUDIO_PERCEPTUAL`) | `<PASS / PERCEPTUAL_AUDIO_PENDING>` | `<structured perceptual_audio_evidence JSON matching MP4 SHA256>` | `<never claim from waveform or naked boolean>` |
| Source Originals Unchanged | `<PASS / FAIL>` | `verify_source_hashes.py` | `<SHA256 pre == post across single/multi roots>` |

## Defects & Open Blockers
- `<List exact P0/P1/P2 defects or blockers with timestamps and reproduction recipes>`
