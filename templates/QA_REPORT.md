# Quality Assurance Report

- **Run ID**: `<YYYYMMDD_HHMMSS_slug>`
- **Platform**: `<os_version / arch>`
- **Concat Binary & Version**: `<verified path & version, or NOT_INSTALLED>`
- **Overall Verified State**: `<exact state from formal state machine — NEVER inflate>`

## Gate Status Table

| Gate | Status | Evidence Path | Notes / Exact Blocker |
| --- | --- | --- | --- |
| M0 / C0 Environment Probe | `<PASS / BLOCKED_ENV>` | `ENV_MATRIX.json` | `<summary>` |
| C0 MCP Connected (`--mcp headless`) | `<PASS / BLOCKED_ENV / FAIL>` | `CONCAT_CAPABILITY_MATRIX.json` | `<summary>` |
| Layer 1 Static & Source Integrity | `<PASS / FAIL>` | `SOURCE_INVENTORY.csv`, `EDL.json` | `<summary>` |
| Layer 2 Preview & Critic | `<PASS / PREVIEW_VISUAL_PENDING / BLOCKED_ENV>` | `PREVIEW_EVIDENCE/`, `CRITIC_NOTES.md` | `<summary>` |
| Native Project Save / Reopen | `<PASS / BLOCKED_ENV / FAIL>` | `<reopen diff>` | `<summary>` |
| Layer 3 Concat MP4 Export | `<PASS / BLOCKED_ENV / FAIL>` | `POST_EXPORT_QA.json` | `<summary>` |
| Audio Signal QA (`PASS_AUDIO_SIGNAL`) | `<PASS / BLOCKED_ENV / FAIL>` | `POST_EXPORT_QA.json` | `<measured RMS/peak>` |
| Audio Perceptual QA (`PASS_AUDIO_PERCEPTUAL`) | `<PASS / PERCEPTUAL_AUDIO_PENDING>` | `<human listening log>` | `<never claim from waveform alone>` |
| Source Originals Unchanged | `<PASS / FAIL>` | `verify_source_hashes.py` | `<SHA256 pre == post>` |

## Defects & Open Blockers
- `<List exact P0/P1/P2 defects or blockers with timestamps and reproduction recipes>`
