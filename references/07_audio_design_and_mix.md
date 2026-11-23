# 07 — Local Voice, TTS & Sound Design (Phase P5)

Sound carries half the perceived professionalism of a video. Never assume a timeline waveform screenshot means the audio actually sounds clean.

## 1. Voiceover Policy (Optional & Local-First)

- Voiceover is **optional**: skip synthetic narration whenever natural sound, talking-head speech, or visual montage rhythm works better.
- **English-US natural voice (when requested/appropriate)**:
  - Audition 2–3 voice options suited to the niche (calm storyteller, clear tutorial instructor, warm brand presenter) — never one robotic default for every niche.
  - **Primary local engine**: Audited **Kokoro** local TTS (verify code license, weights license, and voice preset licenses separately; avoid downloading duplicate Kokoro models if Concat already bundles one).
  - **Secondary local engine**: **Chatterbox** or **Pocket TTS** only when prosody/authorized cloning is genuinely needed, hardware is sufficient, and OS compatibility is met (note: Intel macOS 12 cannot run ONNX-based Chatterbox — requires macOS 13.4+).
  - **Voice cloning ethics**: Strictly forbidden without explicit owner/speaker authorization; never imitate celebrities, creators, or third parties.
  - **macOS `say` / Windows SAPI**: Never default production voices; use only as an explicitly approved fallback with quality/license disclosure.
- **MCP check**: Verify `tools/list` before assuming Concat exposes an MCP TTS tool. If absent (expected when TTS is GUI-only), synthesize audited local WAV/PCM externally and import via `media_import`.
- **Zero paid TTS/STT by default**: Never call ElevenLabs or paid cloud speech APIs without `STOP_FOR_COST_APPROVAL`.

## 2. Speech Craft & Normalization

- Keep natural phrasing and semantic pauses (0.25–0.6s at narrative turns); do not insert mechanical gaps after every word or speed-cram scripts.
- Maintain a clean script sheet (`SCRIPT_AND_VO.md`) with pronunciation notes and cue timings; never fabricate audio files.
- Cut video/speech at completed phonemes/sentences; apply gentle micro-fades at clip boundaries to prevent clicks/pops where supported.

## 3. Music, SFX & Mix Architecture (`SOUND_CUE_SHEET.csv`)

Separate audio onto distinct editable native Concat tracks:
1. **Dialogue / VO Track**: Primary intelligibility anchor at mobile phone volume.
2. **BGM Track**: Matches emotional arc; sits clearly beneath voice and ducks cleanly during spoken beats using tested Concat keyframes/volume controls.
3. **SFX Track**: Subtle, motivated cues (whoosh, UI click, room tone, impact, soft chime) below narration unless an intentional beat demands accent. Use a cohesive motif rather than random loud sound effects.

### Signal QA vs Owner Human Perceptual QA (Strict Separation)
- **`PASS_AUDIO_SIGNAL`**: Measured on the **real exported MP4** via `verify_export.py` (`volumedetect`, `ebur128=peak=true` integrated LUFS + true peak, and `silencedetect` including trailing EOF silence).
  - Unexpected silence dropouts overlapping active audio -> `FAIL_UNEXPECTED_AUDIO_DROPOUT` (planned silence/pause cues declared in `SOUND_CUE_SHEET.csv` / EDL are classified as `SILENCE_PLANNED`).
  - Missing/unparseable `ebur128` LUFS/true peak when required -> `MEASUREMENT_INCOMPLETE` (never silent PASS).
  - `--allow-silent` cannot override ANY mandatory planned audio (`audio_expected_by_plan`: VO, BGM, SFX, ambience, or UI clicks) unless explicitly omitted/optional in a silent editorial plan (`FAIL_SILENT_OVERRIDE_CONFLICTS_WITH_AUDIO_PLAN`).
- **`PASS_AUDIO_PERCEPTUAL`**: Requires actual owner playback review recorded as structured `OWNER_HUMAN` evidence (`reviewer_type: "OWNER_HUMAN"`, `confirmation_source: "OWNER_INTERACTION_RECORDED"`, `playback_confirmed: true`, matching `mp4_sha256`, `reviewed_at >= exported_at`, and content-aware auditory checklist — `"N/A"` is forbidden on `intelligibility`/`sync` for VO, `ducking` for BGM+VO, and `pops_clicks` for SFX). Agent/bot self-attestation is rejected and remains **`PERCEPTUAL_AUDIO_PENDING`**.
