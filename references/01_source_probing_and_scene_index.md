# 01 — Read-Only Source Probing & Visual Scene Indexing (Phase P0)

All source files supplied by the user are **strictly read-only**. Never modify, rename, move, re-encode in place, or delete original footage.

## 1. Bounded Discovery & Security Guards

Use `python3 scripts/probe_sources.py` with explicit bounds:
- `max_depth` (default `5`), `max_files` (default `200`), `max_file_gb` (default `8.0`), `max_total_gb` (default `40.0`), per-file `timeout_s` (default `20`).
- Reject symlink loops, symlink escapes outside approved input roots, path traversal (`..`), and protected OS directories (`/System`, `/Library`, `C:\Windows`, etc.).
- Never scan entire drives (`/` or `D:\`) or `~/Downloads` indiscriminately.
- Record streamed SHA-256 hashes (chunked I/O, never loading whole video files into RAM) before editing and verify zero drift after editing with `python3 scripts/verify_source_hashes.py`.

## 2. Metadata Extraction (`ffprobe` Subprocess)

For each discovered media file, extract via bounded `ffprobe` subprocess (argv array, never shell interpolation):
- `source_id` (`U001`, `U002`, ...), relative/sanitized label (avoid leaking private absolute home paths into public reports), extension, byte size, `sha256`.
- Video stream: codec, pixel format, width, height, display aspect ratio, rotation metadata, rational FPS (`r_frame_rate`), average FPS (`avg_frame_rate`), VFR suspicion flag (`r_frame_rate` vs `avg_frame_rate` divergence), color space / transfer (flag HDR/10-bit), duration.
- Audio stream: codec, sample rate, channels, duration, absence flag (`has_audio`).
- Platform concurrency rule: Run independent read-only `ffprobe`/SHA-256 workers in a bounded pool (2–4 workers max); isolate subprocesses cleanly on both macOS and Windows.

## 3. Compact Visual Scene Indexing & Speech Handling

- **Contact sheets first**: Sample bounded stills (e.g., evenly spaced + scene change candidates, capped pixel budget) instead of decoding every frame.
- **Visual truth check**: Note real subjects, camera orientation, legibility of UI/text, watermarks, loading spinners, repeated takes, blur, and any accidental PII (messages, browser tabs, emails, user IDs).
- **Speech vs silent footage**:
  - Silent or music-only footage -> visual shot indexing only; **never** run expensive or paid transcription.
  - Speech footage -> reuse user-provided transcript first; if ASR is needed, use an audited local model (e.g., Whisper local) with word timestamps and confidence scores.
- **Pre-transcode provenance**: If VFR, exotic codec, or HDR input is proven incompatible with Concat on the host, create a staged mezzanine copy inside the run directory, record its exact ffmpeg command and parent `source_id`/`sha256`, and leave the original untouched.

## 4. Mandatory Rights Tagging & Truth Labels

Every source in `SOURCE_INVENTORY.csv` MUST carry one explicit rights tag:
- `OWNED`: User-owned original media.
- `LICENSED`: Verified third-party asset with documented commercial license in `LICENSE_LEDGER.csv`.
- `GENERATED`: Locally generated asset (e.g., approved TTS WAV or clean synthetic test clip) with tool/model license logged.
- `ANALYSIS_ONLY`: Competitor, reference, or copyrighted media used solely for style study. **Hard-blocked from EDL and Concat `media_import`.**
- `UNKNOWN_RIGHTS`: Provenance not yet confirmed. **Hard-blocked from final export until verified.**

In `SOURCE_TRUTH.md`, separate facts into `VERIFIED` (directly observed in frames/metadata), `INFERRED` (editorial deduction), and `UNKNOWN` (cannot be asserted in script/CTA).
