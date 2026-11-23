# Quality Assurance Report (Two-Axis — Never Conflate Code vs Runtime)

- **Run ID**: `<YYYYMMDD_HHMMSS_slug>`
- **Platform**: `<os_version / arch>`
- **Concat Binary & Version**: `<verified path, binary_source & version, or NOT_INSTALLED>`
- **QA Level / Phase / Policy**: `<technical | release>` / `<C1 | C2 | C4>` / `<technical-smoke | full-creative>`

## Axis 1 — `CODE_QUALITY` (Offline Static, Unit, Negative & Safety Gates)
- `GLOBAL_SKILL_STATIC`: `<PASS / FAIL>`
- `CODE_QA_REGRESSION`: `<PASS N/N | FAIL X | SKIP Y>` (2x deterministic runs under pinned `PYTHONHASHSEED`)
- `SOURCE_SAFETY_NO_DRIFT`: `<PASS / FAIL>`

## Axis 2 — `RUNTIME` (Live Host Concat MCP & Editorial Verification)
- `C0` (`MCP_CONNECTED`): `<PASS / BLOCKED_ENV_CONCAT_BINARY_MISSING / FAIL>`
- `C1` (`C1_TECHNICAL_E2E` / `C1_NATIVE_EXPORT_VERIFIED`): `<PASS / C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING / BLOCKED_ENV / PENDING / FAIL>`
- `C2` (`CREATIVE_RELEASE`): `<PASS / PENDING / BLOCKED_ENV / FAIL>` (requires `OWNER_HUMAN` listening evidence + `PASS_SOURCE_INTEGRITY`)
- `C4` (`BATCH_AND_LONGFORM_STRESS`): `<PASS / PENDING / BLOCKED_ENV>`
- `PRODUCTION_READY`: `<FALSE unless C1 + C2 + C4 + OWNER_HUMAN all PASS>`

## Detailed Gate Table

| Gate | Axis | Status | Evidence Path | Notes / Exact Blocker |
| --- | --- | --- | --- | --- |
| Static Package & Manifest Hashes | `CODE_QUALITY` | `<PASS / FAIL>` | `check_skill_package.py` | `<45+ files, 0 secrets>` |
| Unit / Negative / Regression (2x) | `CODE_QUALITY` | `<PASS / FAIL>` | `logs/pytest_run_1.txt`, `logs/pytest_run_2.txt` | `<deterministic counts>` |
| M0 / C0 Env & Disk Guard | `RUNTIME` | `<PASS / BLOCKED_LOW_DISK / BLOCKED_ENV>` | `ENV_MATRIX.json` | `<decoupled OS/disk/binary/QA tools>` |
| C0 Live MCP (`--mcp headless`) | `RUNTIME` | `<PASS / BLOCKED_ENV / FAIL>` | `CONCAT_CAPABILITY_MATRIX.json` | `<live initialize + tools/list + concat_version>` |
| Layer 1 Release EDL & Rights (`--validation-mode release --run-dir ...`) | `RUNTIME` | `<PASS_EDL_VALID_FOR_RELEASE / FAIL>` | `SOURCE_INVENTORY.csv`, `EDL.json`, `LICENSE_LEDGER.csv` | `<duplicate-free, anchored claims, archived licenses>` |
| Layer 2 Live `preview_frame` & Critic | `RUNTIME` | `<PASS / BLOCKED_ENV / FAIL>` | `PREVIEW_MANIFEST.json`, `CRITIC_NOTES.md` | `<CONCAT_MCP_PREVIEW_FRAME origin + SSIM/PSNR>` |
| Native Save / Reopen Fingerprint | `RUNTIME` | `<PASS / BLOCKED_ENV / FAIL>` | `MCP_EXPORT_EVIDENCE.json` | `<before_save == after_reopen>` |
| Layer 3 Concat MP4 Export (`--qa-level release`) | `RUNTIME` | `<PASS_END_TO_END_EXPORT_QA / C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING / PENDING_PERCEPTUAL_AUDIO / BLOCKED_ENV / FAIL>` | `POST_EXPORT_QA.json`, `MCP_EXPORT_EVIDENCE.json` | `<LIVE_MCP_EXPORT_EVIDENCE + matched job_ids + full decode>` |
| Audio Signal QA (`PASS_AUDIO_SIGNAL`) | `RUNTIME` | `<PASS / MEASUREMENT_INCOMPLETE / FAIL_UNEXPECTED_AUDIO_DROPOUT / FAIL_AUDIO_CLIP / BLOCKED_ENV>` | `POST_EXPORT_QA.json` | `<volumedetect + ebur128 LUFS/true peak + EOF silence>` |
| Owner Human Perceptual Audio | `RUNTIME` | `<PASS_AUDIO_PERCEPTUAL / PERCEPTUAL_AUDIO_PENDING>` | `<OWNER_HUMAN JSON matching MP4 SHA256>` | `<rejects AGENT/BOT self-attestation>` |
| Source Originals Unchanged | `CODE_QUALITY` / `RUNTIME` | `<PASS_SOURCE_INTEGRITY / FAIL>` | `verify_source_hashes.py` | `<SHA256 pre == post>` |

## Defects & Open Blockers
- `<List exact P0/P1/P2 defects or blockers with timestamps and reproduction recipes>`
