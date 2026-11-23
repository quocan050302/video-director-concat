#!/usr/bin/env python3
"""Fail-closed post-export QA for Concat-exported MP4 files (QA.R2 hardened).

Strict separation of axes & trust boundaries:
- qa_level="technical": Standalone media diagnostic (probe, full decode, spec, black/freeze + EOF,
  volumedetect + ebur128 LUFS/true peak + silencedetect dropouts). Returns PASS_TECHNICAL_ONLY at most.
- qa_level="release": Enforces gate_phase (C1|C2|C4) and release_policy (technical-smoke|full-creative):
  * Separates UNIT_SIMULATED_PROVENANCE (never live_concat_verified or PASS_END_TO_END_EXPORT_QA)
    from LIVE_MCP_EXPORT_EVIDENCE (requires complete live tool trace, matching start/wait job IDs,
    plausible timestamp order, matching save/reopen fingerprints, non-symlink output/project roots,
    and CONCAT_MCP_PREVIEW_FRAME preview provenance).
  * Restricts technical-smoke strictly to C1 (sets technical_e2e_gate_pass=True,
    creative_release_gate_pass=False, release_gate_pass=False). Rejects technical-smoke on C2/C4.
  * Requires OWNER_HUMAN listening evidence with auditory checklist & matching MP4 SHA-256 for
    PASS_AUDIO_PERCEPTUAL (rejects agent/bot self-attestation).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
REQUIRED_LIVE_MCP_TOOLS = {
    "project_create",
    "timeline_read",
    "preview_frame",
    "project_save",
    "project_close",
    "project_open",
    "export_start",
    "export_wait",
}
REQUIRED_AUDITORY_CHECKLIST_KEYS = {
    "intelligibility",
    "pops_clicks",
    "ducking",
    "sync",
    "no_unexpected_silence",
}
NON_HUMAN_REVIEWER_TYPES = {"AGENT", "BOT", "MODEL", "AI", "AUTOMATED", "SCRIPT"}


def _stream_sha256(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _parse_iso_ts(raw: Any) -> dt.datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except ValueError:
        return None


def probe_export(mp4: str | Path, timeout_s: int = 30, require_full_decode: bool = True) -> dict[str, Any]:
    """Validate real MP4 exists, is non-empty, not .tmp, probes cleanly, and passes full decode."""
    p = Path(mp4)
    if not p.exists() or not p.is_file():
        return {"status": "FAIL_EXPORT_MISSING", "error": f"MP4 file does not exist: {p}"}
    if p.suffix.lower() != ".mp4" or p.name.endswith(".tmp"):
        return {"status": "FAIL_NOT_FINAL_MP4", "error": f"Rejected non-final export path: {p.name}"}
    size = p.stat().st_size
    if size == 0:
        return {"status": "FAIL_EXPORT_EMPTY", "error": "MP4 file is 0 bytes"}

    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return {"status": "BLOCKED_ENV_FFPROBE_MISSING", "error": "ffprobe not available"}

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(p),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "FAIL_EXPORT_DECODE", "error": "ffprobe timed out"}
    except OSError as exc:
        return {"status": "FAIL_EXPORT_DECODE", "error": str(exc)}

    if proc.returncode != 0:
        return {"status": "FAIL_EXPORT_DECODE", "error": (proc.stderr or proc.stdout).strip()[:400]}

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "FAIL_EXPORT_DECODE", "error": f"Invalid ffprobe JSON: {exc}"}

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v_stream:
        return {"status": "FAIL_EXPORT_DECODE", "error": "No video stream in MP4"}

    try:
        duration_s = float(fmt.get("duration") or v_stream.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration_s = 0.0
    if not math.isfinite(duration_s) or duration_s <= 0.0:
        return {"status": "FAIL_EXPORT_DECODE", "error": "Export duration <= 0s"}

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        if require_full_decode:
            return {"status": "BLOCKED_ENV_FFMPEG_MISSING", "error": "ffmpeg required for full decode verification"}
        decode_verified = False
    else:
        d_cmd = [ffmpeg_bin, "-v", "error", "-i", str(p), "-f", "null", "-"]
        try:
            d_proc = subprocess.run(d_cmd, capture_output=True, text=True, timeout=max(timeout_s, 60), check=False)
        except subprocess.TimeoutExpired:
            return {"status": "FAIL_EXPORT_DECODE", "error": "ffmpeg full decode timed out"}
        except OSError as exc:
            return {"status": "FAIL_EXPORT_DECODE", "error": str(exc)}
        if d_proc.returncode != 0 or d_proc.stderr.strip():
            return {
                "status": "FAIL_EXPORT_DECODE",
                "error": (d_proc.stderr or f"ffmpeg exit={d_proc.returncode}").strip()[:400],
            }
        decode_verified = True

    return {
        "status": "PASS_PROBE_AND_DECODE",
        "decode_verified": decode_verified,
        "path": str(p.resolve()),
        "raw_path": str(p),
        "is_symlink": p.is_symlink(),
        "bytes": size,
        "sha256": _stream_sha256(p),
        "duration_s": round(duration_s, 4),
        "width": int(v_stream.get("width", 0)),
        "height": int(v_stream.get("height", 0)),
        "video_codec": v_stream.get("codec_name", ""),
        "pix_fmt": v_stream.get("pix_fmt", ""),
        "r_frame_rate": v_stream.get("r_frame_rate", ""),
        "avg_frame_rate": v_stream.get("avg_frame_rate", ""),
        "has_audio": a_stream is not None,
        "audio_codec": (a_stream or {}).get("codec_name", ""),
        "sample_rate": int(a_stream["sample_rate"]) if a_stream and a_stream.get("sample_rate") else 0,
        "channels": int(a_stream["channels"]) if a_stream and a_stream.get("channels") else 0,
    }


def verify_dimensions_fps_duration(probe_data: dict[str, Any], spec: dict[str, Any] | None) -> dict[str, Any]:
    if probe_data.get("status") != "PASS_PROBE_AND_DECODE":
        return {"status": "FAIL", "errors": ["PROBE_DID_NOT_PASS"]}
    if not spec:
        return {"status": "SKIPPED_NOT_APPLICABLE", "errors": []}

    errors: list[str] = []
    if spec.get("width") and int(probe_data["width"]) != int(spec["width"]):
        errors.append(f"WIDTH_MISMATCH: actual={probe_data['width']} expected={spec['width']}")
    if spec.get("height") and int(probe_data["height"]) != int(spec["height"]):
        errors.append(f"HEIGHT_MISMATCH: actual={probe_data['height']} expected={spec['height']}")

    if spec.get("timeline_fps") and probe_data.get("avg_frame_rate"):
        try:
            exp_fps = float(Fraction(str(spec["timeline_fps"])))
            act_fps = float(Fraction(str(probe_data["avg_frame_rate"])))
            if abs(act_fps - exp_fps) > 0.5:
                errors.append(f"FPS_MISMATCH: actual={act_fps:.2f} expected={exp_fps:.2f}")
        except (ValueError, ZeroDivisionError):
            errors.append("FPS_PARSE_ERROR")

    if spec.get("expected_duration_s"):
        exp_dur = float(spec["expected_duration_s"])
        tol = float(spec.get("duration_tolerance_s", 0.25))
        if abs(float(probe_data["duration_s"]) - exp_dur) > tol:
            errors.append(f"DURATION_MISMATCH: actual={probe_data['duration_s']}s expected={exp_dur}s (+/-{tol}s)")

    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def _edl_intentional_windows(edl: dict[str, Any] | None, flag_key: str) -> list[tuple[float, float]]:
    if not edl:
        return []
    fps = float(Fraction(str((edl.get("output_spec") or {}).get("timeline_fps", "30/1"))))
    windows: list[tuple[float, float]] = []
    for shot in edl.get("shots", []):
        if isinstance(shot, dict) and shot.get(flag_key):
            windows.append((shot["output_in_frame"] / fps, shot["output_out_frame"] / fps))
    return windows


def _cue_planned_silence_windows(cue_sheet: list[dict[str, Any]] | None, edl: dict[str, Any] | None = None) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for cue in cue_sheet or []:
        if not isinstance(cue, dict):
            continue
        ctype = str(cue.get("cue_type") or "").upper()
        if any(k in ctype for k in ("SILENCE", "PAUSE", "GAP")):
            try:
                windows.append((float(cue["timeline_in_s"]), float(cue["timeline_out_s"])))
            except (KeyError, TypeError, ValueError):
                continue
    windows.extend(_edl_intentional_windows(edl, "intentional_silence"))
    return windows


def _interval_covered(start: float, end: float, allowed: list[tuple[float, float]], tol: float = 0.2) -> bool:
    for a_s, a_e in allowed:
        if start >= a_s - tol and end <= a_e + tol:
            return True
    return False


def detect_unintended_blacks_and_freezes(
    mp4: str | Path,
    edl: dict[str, Any] | None = None,
    duration_s: float | None = None,
    timeout_s: int = 60,
) -> dict[str, Any]:
    """Run ffmpeg blackdetect/freezedetect with strict exit-code checks and EOF trailing freeze closure."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return {"status": "BLOCKED_ENV_FFMPEG_MISSING", "unintended_blacks": [], "unintended_freezes": []}

    if duration_s is None:
        pr = probe_export(mp4, timeout_s=min(timeout_s, 30), require_full_decode=False)
        duration_s = float(pr.get("duration_s") or 0.0) if pr.get("status") == "PASS_PROBE_AND_DECODE" else 0.0

    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-i", str(mp4),
        "-vf", "blackdetect=d=0.35:pix_th=0.08,freezedetect=n=-60dB:d=1.5",
        "-an",
        "-f", "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "FAIL_DETECTION_TIMEOUT", "unintended_blacks": [], "unintended_freezes": []}
    except OSError as exc:
        return {"status": "FAIL_BLACK_FREEZE_FFMPEG_ERROR", "error": str(exc), "unintended_blacks": [], "unintended_freezes": []}

    if proc.returncode != 0:
        return {
            "status": "FAIL_BLACK_FREEZE_FFMPEG_ERROR",
            "error": (proc.stderr or f"exit={proc.returncode}").strip()[-300:],
            "unintended_blacks": [],
            "unintended_freezes": [],
        }

    stderr = proc.stderr or ""
    allowed_blacks = _edl_intentional_windows(edl, "intentional_black")
    allowed_freezes = _edl_intentional_windows(edl, "intentional_freeze")

    unintended_blacks = []
    intentional_blacks = []
    for m in re.finditer(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", stderr):
        bs, be, bd = float(m.group(1)), float(m.group(2)), float(m.group(3))
        rec = {"start_s": bs, "end_s": be, "duration_s": bd}
        if _interval_covered(bs, be, allowed_blacks):
            intentional_blacks.append(rec)
        else:
            unintended_blacks.append(rec)

    unintended_freezes = []
    intentional_freezes = []
    starts = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", stderr)]
    if len(starts) > len(ends):
        eof_t = duration_s if duration_s and duration_s > starts[-1] else starts[-1] + 1.5
        while len(ends) < len(starts):
            ends.append(round(eof_t, 3))

    for fs, fe in zip(starts, ends):
        rec = {"start_s": fs, "end_s": fe, "duration_s": round(max(0.0, fe - fs), 3)}
        if _interval_covered(fs, fe, allowed_freezes):
            intentional_freezes.append(rec)
        else:
            unintended_freezes.append(rec)

    status = "PASS" if (not unintended_blacks and not unintended_freezes) else "FAIL_UNINTENDED_BLACK_OR_FREEZE"
    return {
        "status": status,
        "unintended_blacks": unintended_blacks,
        "intentional_blacks": intentional_blacks,
        "unintended_freezes": unintended_freezes,
        "intentional_freezes": intentional_freezes,
    }


def _edl_requires_audio(edl: dict[str, Any] | None, cue_sheet: list[dict[str, Any]] | None) -> bool:
    if edl:
        vp = str(edl.get("voice_policy") or "").strip().upper()
        if vp and vp not in {"NONE", "SILENT", "OFF"}:
            return True
        for ac in edl.get("audio_tracks", []):
            if isinstance(ac, dict):
                tr = str(ac.get("track") or "").upper()
                if any(k in tr for k in ("VO", "VOICE", "DIALOG", "SPEECH")):
                    return True
    for cue in cue_sheet or []:
        if isinstance(cue, dict):
            ct = str(cue.get("cue_type") or "").upper()
            if any(k in ct for k in ("VO", "VOICE", "DIALOG", "SPEECH")):
                return True
    return False


def measure_audio_segments(
    mp4: str | Path,
    cue_sheet: list[dict[str, Any]] | None = None,
    edl: dict[str, Any] | None = None,
    require_audio: bool = True,
    require_lufs_and_peak: bool = True,
    probe_data: dict[str, Any] | None = None,
    max_true_peak_dbfs: float = -0.05,
    timeout_s: int = 60,
) -> dict[str, Any]:
    """Measure volumedetect, EBU R128 LUFS/true peak, and silencedetect (including EOF silence) against planned cues."""
    if not require_audio and _edl_requires_audio(edl, cue_sheet):
        return {
            "audio_signal_status": "FAIL_SILENT_OVERRIDE_CONFLICTS_WITH_AUDIO_PLAN",
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
            "unexpected_silence_dropouts": [],
            "planned_silences": [],
        }

    probe = probe_data or probe_export(mp4, timeout_s=min(timeout_s, 30), require_full_decode=False)
    if probe.get("status") != "PASS_PROBE_AND_DECODE":
        return {
            "audio_signal_status": "FAIL_EXPORT_INVALID",
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
        }

    if not probe.get("has_audio"):
        return {
            "audio_signal_status": "FAIL_NO_AUDIO_STREAM" if require_audio else "SKIPPED_SILENT_MODE",
            "audio_perceptual_status": "SKIPPED_SILENT_MODE" if not require_audio else "PERCEPTUAL_AUDIO_PENDING",
            "mean_volume_db": None,
            "max_volume_db": None,
            "integrated_lufs": None,
            "true_peak_dbfs": None,
            "silence_dropouts": [],
            "unexpected_silence_dropouts": [],
            "planned_silences": [],
        }

    if int(probe.get("sample_rate") or 0) <= 0 or int(probe.get("channels") or 0) <= 0:
        return {
            "audio_signal_status": "FAIL_AUDIO_STREAM_INVALID",
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
        }

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return {
            "audio_signal_status": "BLOCKED_ENV_FFMPEG_MISSING",
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
        }

    cmd_vol = [
        ffmpeg_bin, "-hide_banner", "-i", str(mp4), "-vn",
        "-af", "volumedetect,silencedetect=n=-55dB:d=1.5",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd_vol, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return {"audio_signal_status": "FAIL_AUDIO_TIMEOUT", "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING"}
    except OSError as exc:
        return {"audio_signal_status": "FAIL_AUDIO_UNMEASURABLE", "error": str(exc), "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING"}

    if proc.returncode != 0:
        return {
            "audio_signal_status": "FAIL_AUDIO_FFMPEG_ERROR",
            "error": (proc.stderr or "")[-300:],
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
        }

    stderr = proc.stderr or ""
    m_mean = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", stderr)
    m_max = re.search(r"max_volume:\s*([-\d.]+)\s*dB", stderr)
    mean_db = float(m_mean.group(1)) if m_mean else None
    max_db = float(m_max.group(1)) if m_max else None

    # Parse BOTH silence_start and silence_end, closing trailing EOF silence at duration_s
    dur_s = float(probe.get("duration_s") or 0.0)
    s_starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", stderr)]
    s_ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", stderr)]
    if len(s_starts) > len(s_ends):
        eof_t = dur_s if dur_s > s_starts[-1] else s_starts[-1] + 1.5
        while len(s_ends) < len(s_starts):
            s_ends.append(round(eof_t, 3))

    planned_windows = _cue_planned_silence_windows(cue_sheet, edl)
    all_silences: list[dict[str, float]] = []
    planned_silences: list[dict[str, float]] = []
    unexpected_dropouts: list[dict[str, float]] = []
    for ss, se in zip(s_starts, s_ends):
        rec = {"start_s": ss, "end_s": se, "duration_s": round(max(0.0, se - ss), 3)}
        all_silences.append(rec)
        if _interval_covered(ss, se, planned_windows):
            planned_silences.append(rec)
        else:
            unexpected_dropouts.append(rec)

    integrated_lufs: float | None = None
    true_peak_dbfs: float | None = None
    cmd_ebu = [ffmpeg_bin, "-hide_banner", "-i", str(mp4), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]
    try:
        p_ebu = subprocess.run(cmd_ebu, capture_output=True, text=True, timeout=timeout_s, check=False)
        if p_ebu.returncode == 0:
            m_i = re.search(r"Summary:.*?I:\s*([-\d.]+)\s*LUFS", p_ebu.stderr or "", flags=re.S)
            m_tp = re.search(r"True peak:.*?Peak:\s*([-\d.]+)\s*dBFS", p_ebu.stderr or "", flags=re.S)
            if m_i:
                integrated_lufs = float(m_i.group(1))
            if m_tp:
                true_peak_dbfs = float(m_tp.group(1))
    except (OSError, subprocess.SubprocessError):
        pass

    if mean_db is None or max_db is None:
        sig_status = "MEASUREMENT_INCOMPLETE"
    elif require_lufs_and_peak and (integrated_lufs is None or true_peak_dbfs is None):
        sig_status = "MEASUREMENT_INCOMPLETE"
    elif max_db >= max_true_peak_dbfs or (true_peak_dbfs is not None and true_peak_dbfs >= max_true_peak_dbfs):
        sig_status = "FAIL_AUDIO_CLIP"
    elif mean_db <= -75.0:
        sig_status = "FAIL_AUDIO_SILENT"
    elif unexpected_dropouts:
        sig_status = "FAIL_UNEXPECTED_AUDIO_DROPOUT"
    else:
        sig_status = "PASS_AUDIO_SIGNAL"

    return {
        "audio_signal_status": sig_status,
        "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
        "sample_rate": int(probe["sample_rate"]),
        "channels": int(probe["channels"]),
        "mean_volume_db": mean_db,
        "max_volume_db": max_db,
        "integrated_lufs": integrated_lufs,
        "true_peak_dbfs": true_peak_dbfs,
        "silence_dropouts": all_silences,
        "unexpected_silence_dropouts": unexpected_dropouts,
        "planned_silences": planned_silences,
        "cue_count_referenced": len(cue_sheet or []),
    }


def _probe_image_dims(img_path: Path, timeout_s: int = 10) -> tuple[int, int] | None:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None
    cmd = [ffprobe_bin, "-v", "error", "-print_format", "json", "-show_streams", str(img_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        if proc.returncode != 0:
            return None
        streams = json.loads(proc.stdout).get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        if v and v.get("width") and v.get("height"):
            return int(v["width"]), int(v["height"])
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None
    return None


def compare_preview_export_frame(
    preview_path: str | Path,
    mp4: str | Path,
    timestamp_s: float,
    expected_dims: tuple[int, int] | None = None,
    timeline_fps: str | None = None,
    min_ssim: float = 0.75,
    min_psnr_db: float = 20.0,
    timeout_s: int = 30,
) -> dict[str, Any]:
    prev = Path(preview_path)
    if not prev.exists() or not prev.is_file() or prev.stat().st_size == 0:
        return {"status": "FAIL_PREVIEW_MISSING", "preview_path": str(prev), "timestamp_s": timestamp_s}

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return {"status": "BLOCKED_ENV_FFMPEG_MISSING", "preview_path": str(prev), "timestamp_s": timestamp_s}

    prev_sha = _stream_sha256(prev)
    prev_dims = _probe_image_dims(prev)
    if prev_dims is None:
        return {"status": "FAIL_PREVIEW_UNREADABLE", "preview_path": str(prev), "preview_sha256": prev_sha, "timestamp_s": timestamp_s}

    if expected_dims and prev_dims != expected_dims:
        return {
            "status": "FAIL_PREVIEW_DIMENSION_MISMATCH",
            "preview_path": str(prev),
            "preview_sha256": prev_sha,
            "preview_dims": list(prev_dims),
            "export_dims": list(expected_dims),
            "timestamp_s": timestamp_s,
        }

    aligned_t = max(0.0, float(timestamp_s))
    if timeline_fps:
        try:
            fps = float(Fraction(str(timeline_fps)))
            if fps > 0:
                aligned_t = round(round(aligned_t * fps) / fps, 6)
        except (ValueError, ZeroDivisionError):
            pass

    cmd = [
        ffmpeg_bin, "-hide_banner",
        "-i", str(prev),
        "-ss", f"{aligned_t:.6f}",
        "-i", str(mp4),
        "-frames:v", "1",
        "-lavfi", "[0:v]split=2[p1][p2];[1:v]split=2[e1][e2];[p1][e1]ssim;[p2][e2]psnr",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "FAIL_COMPARE_TIMEOUT", "preview_path": str(prev), "preview_sha256": prev_sha, "timestamp_s": aligned_t}
    except OSError as exc:
        return {"status": "FAIL_PREVIEW_MISMATCH", "error": str(exc), "preview_path": str(prev), "timestamp_s": aligned_t}

    if proc.returncode != 0:
        return {
            "status": "FAIL_PREVIEW_MISMATCH",
            "preview_path": str(prev),
            "preview_sha256": prev_sha,
            "timestamp_s": aligned_t,
            "detail": (proc.stderr or f"exit={proc.returncode}")[-300:],
        }

    stderr = proc.stderr or ""
    m_psnr = re.search(r"average:([0-9.]+|inf)", stderr)
    m_ssim = re.search(r"All:([0-9.]+)", stderr)
    if not m_psnr or not m_ssim:
        return {
            "status": "FAIL_PREVIEW_MISMATCH",
            "preview_path": str(prev),
            "preview_sha256": prev_sha,
            "timestamp_s": aligned_t,
            "detail": "Missing SSIM/PSNR metrics in ffmpeg output",
        }

    psnr_val = float("inf") if m_psnr.group(1) == "inf" else float(m_psnr.group(1))
    ssim_val = float(m_ssim.group(1))
    passed = ssim_val >= min_ssim and psnr_val >= min_psnr_db
    return {
        "status": "PASS_PREVIEW_MATCH" if passed else "FAIL_PREVIEW_MISMATCH",
        "preview_path": str(prev),
        "preview_sha256": prev_sha,
        "preview_dims": list(prev_dims),
        "timestamp_s": aligned_t,
        "ssim": round(ssim_val, 4),
        "psnr_db": "inf" if psnr_val == float("inf") else round(psnr_val, 2),
    }


def validate_mcp_export_provenance(
    mcp_evidence: dict[str, Any] | None,
    probe_data: dict[str, Any],
    expected_run_id: str | None = None,
    expected_project_id: str | None = None,
) -> dict[str, Any]:
    """Validate orchestrator-captured Concat MCP provenance, tool trace, IDs, timestamps, and paths."""
    trust_note = (
        "Validates orchestrator-captured live MCP trace consistency and on-disk project/preview/export hashes; "
        "self-supplied JSON alone is not external cryptographic attestation."
    )
    if not mcp_evidence or not isinstance(mcp_evidence, dict):
        return {
            "status": "RELEASE_BLOCKED_NO_MCP_PROVENANCE",
            "evidence_source": "MISSING",
            "live_evidence_eligible": False,
            "errors": ["RELEASE_BLOCKED_NO_MCP_PROVENANCE: missing Concat MCP export evidence"],
            "trust_boundary": trust_note,
        }

    errors: list[str] = []
    ev_source = str(mcp_evidence.get("evidence_source") or "UNSPECIFIED").strip().upper()
    if ev_source not in {"LIVE_MCP_EXPORT_EVIDENCE", "UNIT_SIMULATED_PROVENANCE"}:
        errors.append(f"MCP_PROVENANCE_INVALID_EVIDENCE_SOURCE: {ev_source!r}")

    for req_field in (
        "project_id", "run_id", "concat_binary", "concat_binary_sha256",
        "concat_version", "mcp_mode", "output_path", "sha256", "exported_at",
    ):
        if not str(mcp_evidence.get(req_field) or "").strip():
            errors.append(f"MCP_PROVENANCE_MISSING_FIELD: {req_field}")

    bin_sha = str(mcp_evidence.get("concat_binary_sha256") or "").strip()
    if bin_sha and not SHA256_RE.match(bin_sha):
        errors.append("MCP_PROVENANCE_INVALID_BINARY_SHA256")

    if expected_run_id and str(mcp_evidence.get("run_id") or "") != expected_run_id:
        errors.append(f"MCP_PROVENANCE_RUN_ID_MISMATCH: got={mcp_evidence.get('run_id')!r} expected={expected_run_id!r}")
    if expected_project_id and str(mcp_evidence.get("project_id") or "") != expected_project_id:
        errors.append(f"MCP_PROVENANCE_PROJECT_ID_MISMATCH: got={mcp_evidence.get('project_id')!r} expected={expected_project_id!r}")

    if mcp_evidence.get("mcp_mode") not in {"headless", "window"}:
        errors.append(f"MCP_PROVENANCE_INVALID_MODE: {mcp_evidence.get('mcp_mode')!r}")

    ex_start = mcp_evidence.get("export_start") or {}
    ex_wait = mcp_evidence.get("export_wait") or {}
    start_job = str(ex_start.get("job_id") or "").strip() if isinstance(ex_start, dict) else ""
    wait_job = str(ex_wait.get("job_id") or "").strip() if isinstance(ex_wait, dict) else ""
    if not start_job:
        errors.append("MCP_PROVENANCE_MISSING_EXPORT_START_JOB_ID")

    schema_variant = str(mcp_evidence.get("schema_variant") or "").strip()
    if not wait_job:
        if schema_variant == "WAIT_OMITS_JOB_ID_CORRELATED" and isinstance(ex_wait, dict) and str(ex_wait.get("request_correlation_id") or "").strip():
            pass
        else:
            errors.append("MCP_PROVENANCE_MISSING_EXPORT_WAIT_JOB_ID")
    elif start_job and wait_job != start_job:
        errors.append(f"MCP_PROVENANCE_JOB_ID_MISMATCH: start={start_job} wait={wait_job}")

    if not isinstance(ex_wait, dict) or ex_wait.get("exit_ok") is not True or str(ex_wait.get("status", "")).lower() not in {"completed", "succeeded", "done"}:
        errors.append(f"MCP_PROVENANCE_EXPORT_WAIT_NOT_COMPLETED: {ex_wait!r}")

    # Timestamp ordering check (allow 30s practical clock skew)
    ts_start = _parse_iso_ts(ex_start.get("started_at") if isinstance(ex_start, dict) else None)
    ts_wait = _parse_iso_ts(ex_wait.get("completed_at") if isinstance(ex_wait, dict) else None)
    ts_exp = _parse_iso_ts(mcp_evidence.get("exported_at"))
    if ts_exp is None:
        errors.append("MCP_PROVENANCE_INVALID_EXPORTED_AT")
    if ts_start and ts_wait and (ts_wait - ts_start).total_seconds() < -30.0:
        errors.append("MCP_PROVENANCE_TIMESTAMP_INVERTED: export_wait precedes export_start")
    if ts_wait and ts_exp and (ts_exp - ts_wait).total_seconds() < -30.0:
        errors.append("MCP_PROVENANCE_TIMESTAMP_INVERTED: exported_at precedes export_wait")

    # Save / reopen fingerprint consistency
    fp_main = str(mcp_evidence.get("timeline_fingerprint") or "").strip()
    fp_before = str(mcp_evidence.get("timeline_fingerprint_before_save") or fp_main).strip()
    fp_after = str(mcp_evidence.get("timeline_fingerprint_after_reopen") or fp_main).strip()
    if mcp_evidence.get("reopen_verified") is not True or not fp_main:
        errors.append("MCP_PROVENANCE_REOPEN_NOT_VERIFIED")
    elif fp_before != fp_after or fp_before != fp_main:
        errors.append("MCP_PROVENANCE_TIMELINE_FINGERPRINT_DRIFT")

    # Tool trace completeness
    trace = mcp_evidence.get("tool_trace")
    preview_call_ids: set[str] = set()
    if not isinstance(trace, list) or not trace:
        errors.append("MCP_PROVENANCE_MISSING_TOOL_TRACE")
    else:
        ok_tools: set[str] = set()
        for entry in trace:
            if not isinstance(entry, dict):
                continue
            tname = str(entry.get("tool") or "").strip()
            tst = str(entry.get("status") or "").strip().lower()
            cid = str(entry.get("call_id") or "").strip()
            if tname and cid and tst in {"ok", "completed", "succeeded", "pass"}:
                ok_tools.add(tname)
                if tname == "preview_frame":
                    preview_call_ids.add(cid)
        missing_tools = sorted(REQUIRED_LIVE_MCP_TOOLS - ok_tools)
        if missing_tools:
            errors.append(f"MCP_PROVENANCE_INCOMPLETE_TOOL_TRACE: missing={missing_tools}")

    # Native project path check
    proj_path_raw = str(mcp_evidence.get("project_path") or "").strip()
    proj_root_raw = str(mcp_evidence.get("allowed_project_root") or "").strip()
    if not proj_path_raw or not proj_root_raw:
        errors.append("MCP_PROVENANCE_MISSING_PROJECT_PATH_OR_ROOT")
    else:
        pp = Path(proj_path_raw)
        pr = Path(proj_root_raw).resolve()
        if pp.is_symlink():
            errors.append("MCP_PROVENANCE_PROJECT_SYMLINK_FORBIDDEN")
        elif not pp.exists():
            errors.append("MCP_PROVENANCE_PROJECT_PATH_NOT_FOUND")
        else:
            try:
                pp.resolve().relative_to(pr)
            except ValueError:
                errors.append("MCP_PROVENANCE_PROJECT_OUTSIDE_ALLOWED_ROOT")

    # Export output path & symlink escape check
    actual_sha = str(probe_data.get("sha256") or "").lower()
    claimed_sha = str(mcp_evidence.get("sha256") or "").lower()
    if not SHA256_RE.match(claimed_sha) or claimed_sha != actual_sha:
        errors.append("MCP_PROVENANCE_SHA256_MISMATCH")

    claimed_raw = Path(str(mcp_evidence.get("output_path") or ""))
    if claimed_raw.is_symlink() or probe_data.get("is_symlink"):
        errors.append("MCP_PROVENANCE_SYMLINK_ESCAPE_FORBIDDEN")

    actual_path = Path(probe_data.get("path", "")).resolve()
    claimed_path = claimed_raw.resolve()
    if claimed_path != actual_path:
        errors.append("MCP_PROVENANCE_OUTPUT_PATH_MISMATCH")

    allowed_root_raw = mcp_evidence.get("allowed_export_root")
    if allowed_root_raw:
        allowed_root = Path(str(allowed_root_raw)).resolve()
        try:
            actual_path.relative_to(allowed_root)
        except ValueError:
            errors.append("MCP_PROVENANCE_OUTSIDE_ALLOWED_EXPORT_ROOT")
    else:
        errors.append("MCP_PROVENANCE_MISSING_ALLOWED_EXPORT_ROOT")

    is_consistent = not errors
    live_eligible = is_consistent and ev_source == "LIVE_MCP_EXPORT_EVIDENCE"
    status = (
        "PASS_LIVE_MCP_PROVENANCE_CONSISTENT"
        if live_eligible
        else ("PASS_UNIT_SCHEMA_ONLY_NOT_LIVE" if is_consistent else "FAIL_MCP_PROVENANCE")
    )
    return {
        "status": status,
        "evidence_source": ev_source,
        "live_evidence_eligible": live_eligible,
        "preview_call_ids": sorted(preview_call_ids),
        "errors": errors,
        "trust_boundary": trust_note,
    }


def validate_perceptual_audio_evidence(
    evidence: dict[str, Any] | None,
    actual_mp4_sha: str,
) -> dict[str, Any]:
    """Require OWNER_HUMAN playback confirmation, auditory checklist, valid timestamp, and matching MP4 SHA-256."""
    trust_note = "Structured owner-recorded listening confirmation; field presence alone is not cryptographic biometric proof."
    if not evidence or not isinstance(evidence, dict):
        return {"status": "PERCEPTUAL_AUDIO_PENDING", "reason": "NO_OWNER_LISTENING_EVIDENCE", "trust_note": trust_note}

    reviewer_type = str(evidence.get("reviewer_type") or "").strip().upper()
    if reviewer_type in NON_HUMAN_REVIEWER_TYPES or reviewer_type != "OWNER_HUMAN":
        return {
            "status": "PERCEPTUAL_AUDIO_PENDING",
            "reason": f"NON_HUMAN_OR_UNVERIFIED_REVIEWER_REJECTED:{reviewer_type or 'MISSING'}",
            "trust_note": trust_note,
        }

    reviewer = str(evidence.get("reviewer") or "").strip()
    reviewed_ts = _parse_iso_ts(evidence.get("reviewed_at"))
    sha = str(evidence.get("mp4_sha256") or "").strip().lower()
    verdict = str(evidence.get("verdict") or "").strip().upper()
    playback_ok = evidence.get("playback_confirmed") is True
    checklist = evidence.get("auditory_checklist")

    if verdict == "FAIL" and sha == actual_mp4_sha.lower():
        return {"status": "FAIL_AUDIO_PERCEPTUAL", "reason": "OWNER_REJECTED_AUDIO", "trust_note": trust_note}

    if not reviewer or reviewed_ts is None or not playback_ok:
        return {"status": "PERCEPTUAL_AUDIO_PENDING", "reason": "INCOMPLETE_OWNER_LISTENING_METADATA", "trust_note": trust_note}
    if sha != actual_mp4_sha.lower():
        return {"status": "PERCEPTUAL_AUDIO_PENDING", "reason": "AUDIO_EVIDENCE_SHA256_MISMATCH", "trust_note": trust_note}

    if not isinstance(checklist, dict):
        return {"status": "PERCEPTUAL_AUDIO_PENDING", "reason": "MISSING_AUDITORY_CHECKLIST", "trust_note": trust_note}
    missing_items = []
    for k in REQUIRED_AUDITORY_CHECKLIST_KEYS:
        v = checklist.get(k)
        if v is not True and str(v or "").strip().upper() not in {"OK", "PASS", "N/A"}:
            missing_items.append(k)
    if missing_items:
        return {
            "status": "PERCEPTUAL_AUDIO_PENDING",
            "reason": f"INCOMPLETE_AUDITORY_CHECKLIST:{sorted(missing_items)}",
            "trust_note": trust_note,
        }

    if verdict == "PASS":
        return {"status": "PASS_AUDIO_PERCEPTUAL", "reason": "OWNER_HUMAN_CONFIRMED", "trust_note": trust_note}
    return {"status": "PERCEPTUAL_AUDIO_PENDING", "reason": f"VERDICT_NOT_PASS:{verdict or 'EMPTY'}", "trust_note": trust_note}


def write_post_export_qa(report: dict[str, Any], out_path: str | Path) -> None:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _normalize_preview_checks(preview_checks: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in preview_checks or []:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            out.append({"path": str(item[0]), "timestamp_s": float(item[1]), "origin": "UNSPECIFIED_TUPLE"})
    return out


def evaluate_export(
    mp4: str | Path,
    edl: dict[str, Any] | None = None,
    cue_sheet: list[dict[str, Any]] | None = None,
    require_audio: bool = True,
    preview_checks: list[Any] | None = None,
    mcp_export_evidence: dict[str, Any] | None = None,
    perceptual_audio_evidence: dict[str, Any] | None = None,
    qa_level: str = "technical",
    gate_phase: str = "C1",
    release_policy: str = "full-creative",
    allow_technical_release_profile: bool = False,
    expected_run_id: str | None = None,
    expected_project_id: str | None = None,
) -> dict[str, Any]:
    if qa_level not in {"technical", "release"}:
        raise ValueError(f"Unsupported qa_level: {qa_level!r}")
    if gate_phase not in {"C1", "C2", "C4"}:
        raise ValueError(f"Unsupported gate_phase: {gate_phase!r}")
    if release_policy not in {"technical-smoke", "full-creative"}:
        raise ValueError(f"Unsupported release_policy: {release_policy!r}")

    effective_policy = release_policy
    if allow_technical_release_profile:
        effective_policy = "technical-smoke"

    probe = probe_export(mp4, require_full_decode=(qa_level == "release"))
    if probe.get("status") != "PASS_PROBE_AND_DECODE":
        return {
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "qa_level": qa_level,
            "gate_phase": gate_phase,
            "release_policy": effective_policy,
            "overall_status": "FAIL_EXPORT_QA" if not str(probe.get("status", "")).startswith("BLOCKED") else probe["status"],
            "mp4_qa_pass": False,
            "technical_e2e_gate_pass": False,
            "creative_release_gate_pass": False,
            "release_gate_pass": False,
            "live_concat_verified": False,
            "release_blockers": [probe.get("status", "FAIL_EXPORT_PROBE")],
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
            "probe": probe,
        }

    spec = dict((edl or {}).get("output_spec") or {})
    if edl and edl.get("shots") and "expected_duration_s" not in spec:
        fps = float(Fraction(str(spec.get("timeline_fps", "30/1"))))
        max_frame = max(s["output_out_frame"] for s in edl["shots"])
        spec["expected_duration_s"] = round(max_frame / fps, 4)

    dim_check = verify_dimensions_fps_duration(probe, spec if spec else None)
    bf_check = detect_unintended_blacks_and_freezes(mp4, edl, duration_s=probe.get("duration_s"))
    audio_check = measure_audio_segments(mp4, cue_sheet=cue_sheet, edl=edl, require_audio=require_audio, probe_data=probe)

    percep_detail = {"status": audio_check["audio_perceptual_status"], "reason": "NOT_APPLICABLE"}
    if audio_check["audio_signal_status"] == "PASS_AUDIO_SIGNAL":
        percep_detail = validate_perceptual_audio_evidence(perceptual_audio_evidence, probe["sha256"])
        audio_check["audio_perceptual_status"] = percep_detail["status"]
        audio_check["audio_perceptual_detail"] = percep_detail

    exp_dims = (probe["width"], probe["height"]) if probe.get("width") and probe.get("height") else None
    fps_hint = spec.get("timeline_fps") or probe.get("avg_frame_rate")
    norm_previews = _normalize_preview_checks(preview_checks)
    preview_results = []
    for p_item in norm_previews:
        cmp_res = compare_preview_export_frame(
            p_item["path"], mp4, float(p_item["timestamp_s"]),
            expected_dims=exp_dims, timeline_fps=fps_hint,
        )
        cmp_res["origin"] = str(p_item.get("origin") or "UNSPECIFIED")
        cmp_res["tool_call_id"] = str(p_item.get("tool_call_id") or "")
        cmp_res["declared_sha256"] = str(p_item.get("sha256") or "")
        preview_results.append(cmp_res)

    technical_ok = (
        probe.get("decode_verified") is True
        and dim_check["status"] in {"PASS", "SKIPPED_NOT_APPLICABLE"}
        and bf_check["status"] == "PASS"
        and audio_check["audio_signal_status"] in {"PASS_AUDIO_SIGNAL", "SKIPPED_SILENT_MODE"}
        and all(pr["status"] == "PASS_PREVIEW_MATCH" for pr in preview_results)
    )

    if qa_level == "technical":
        return {
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "qa_level": "technical",
            "gate_phase": gate_phase,
            "overall_status": "PASS_TECHNICAL_ONLY" if technical_ok else "FAIL_TECHNICAL_QA",
            "mp4_qa_pass": technical_ok,
            "technical_e2e_gate_pass": False,
            "creative_release_gate_pass": False,
            "release_gate_pass": False,
            "live_concat_verified": False,
            "release_provenance_checked": False,
            "trust_boundary": "STANDALONE_MEDIA_DIAGNOSTIC_DOES_NOT_PROVE_CONCAT_ORIGIN",
            "audio_signal_status": audio_check["audio_signal_status"],
            "audio_perceptual_status": audio_check["audio_perceptual_status"],
            "probe": probe,
            "spec_check": dim_check,
            "black_freeze_check": bf_check,
            "audio_check": audio_check,
            "preview_comparisons": preview_results,
        }

    # --- Strict release mode ---
    release_blockers: list[str] = []
    if gate_phase in {"C2", "C4"} and effective_policy == "technical-smoke":
        release_blockers.append(
            f"INVALID_RELEASE_POLICY_FOR_PHASE: technical-smoke is restricted to C1, forbidden on {gate_phase}"
        )

    prov_check = validate_mcp_export_provenance(
        mcp_export_evidence, probe,
        expected_run_id=expected_run_id, expected_project_id=expected_project_id,
    )
    if prov_check["status"] == "FAIL_MCP_PROVENANCE" or prov_check["status"] == "RELEASE_BLOCKED_NO_MCP_PROVENANCE":
        release_blockers.extend(prov_check["errors"])

    live_evidence_ok = prov_check["live_evidence_eligible"] is True
    if not live_evidence_ok and prov_check["status"] == "PASS_UNIT_SCHEMA_ONLY_NOT_LIVE":
        release_blockers.append("UNIT_SIMULATED_PROVENANCE_CANNOT_CERTIFY_LIVE_RELEASE")

    if not preview_results:
        release_blockers.append("PREVIEW_MISSING: release mode requires non-empty preview_checks")
    else:
        valid_call_ids = set(prov_check.get("preview_call_ids") or [])
        for pr in preview_results:
            if pr["status"] != "PASS_PREVIEW_MATCH":
                release_blockers.append(f"FAIL_PREVIEW_MISMATCH:{pr.get('preview_path')}")
            if pr.get("origin") != "CONCAT_MCP_PREVIEW_FRAME":
                release_blockers.append(f"PREVIEW_ORIGIN_NOT_CONCAT_MCP:{pr.get('origin')}")
            if not pr.get("tool_call_id") or (valid_call_ids and pr["tool_call_id"] not in valid_call_ids):
                release_blockers.append(f"PREVIEW_TOOL_CALL_ID_UNCORRELATED:{pr.get('tool_call_id')!r}")
            if pr.get("declared_sha256") and pr.get("preview_sha256") and pr["declared_sha256"].lower() != pr["preview_sha256"].lower():
                release_blockers.append("PREVIEW_SHA256_MISMATCH")

    if not technical_ok:
        release_blockers.append("FAIL_TECHNICAL_MEDIA_QA")

    percep = audio_check["audio_perceptual_status"]
    if require_audio and percep == "FAIL_AUDIO_PERCEPTUAL":
        release_blockers.append("FAIL_AUDIO_PERCEPTUAL")

    technical_e2e_pass = False
    creative_release_pass = False

    if release_blockers:
        if (
            prov_check["status"] == "PASS_UNIT_SCHEMA_ONLY_NOT_LIVE"
            and technical_ok
            and len(release_blockers) == 1
            and release_blockers[0] == "UNIT_SIMULATED_PROVENANCE_CANNOT_CERTIFY_LIVE_RELEASE"
        ):
            overall = "PASS_SCHEMA_CONSISTENCY_UNIT_ONLY"
        else:
            overall = "FAIL_RELEASE_QA"
    elif require_audio and percep == "PERCEPTUAL_AUDIO_PENDING":
        if gate_phase == "C1" and effective_policy == "technical-smoke":
            overall = "C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING"
            technical_e2e_pass = True
            creative_release_pass = False
        else:
            overall = "PENDING_PERCEPTUAL_AUDIO"
            release_blockers.append("PERCEPTUAL_AUDIO_PENDING")
    else:
        overall = "PASS_END_TO_END_EXPORT_QA"
        technical_e2e_pass = True
        creative_release_pass = True

    return {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "qa_level": "release",
        "gate_phase": gate_phase,
        "release_policy": effective_policy,
        "overall_status": overall,
        "mp4_qa_pass": technical_ok,
        "technical_e2e_gate_pass": technical_e2e_pass,
        "creative_release_gate_pass": creative_release_pass,
        "release_gate_pass": creative_release_pass,
        "live_concat_verified": bool(live_evidence_ok and technical_e2e_pass),
        "release_provenance_checked": True,
        "release_blockers": release_blockers,
        "audio_signal_status": audio_check["audio_signal_status"],
        "audio_perceptual_status": percep,
        "mcp_provenance": prov_check,
        "probe": probe,
        "spec_check": dim_check,
        "black_freeze_check": bf_check,
        "audio_check": audio_check,
        "preview_comparisons": preview_results,
    }


def _load_preview_manifest(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("previews", data) if isinstance(data, dict) else data
    return [item for item in items if isinstance(item, dict) and item.get("path") is not None and item.get("timestamp_s") is not None]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed post-export MP4 QA (technical vs release).")
    parser.add_argument("--mp4", type=Path, required=True, help="Actual exported MP4 path.")
    parser.add_argument("--edl", type=Path, help="Optional EDL JSON for spec & intentional black/freeze/silence checks.")
    parser.add_argument("--qa-level", choices=["technical", "release"], default="technical")
    parser.add_argument("--gate-phase", choices=["C1", "C2", "C4"], default="C1")
    parser.add_argument("--release-policy", choices=["technical-smoke", "full-creative"], default="full-creative")
    parser.add_argument("--mcp-evidence", type=Path, help="MCP export provenance JSON (required for --qa-level release).")
    parser.add_argument("--preview-manifest", type=Path, help="Preview manifest JSON (required for --qa-level release).")
    parser.add_argument("--perceptual-evidence", type=Path, help="Optional OWNER_HUMAN listening confirmation JSON.")
    parser.add_argument("--expected-run-id", type=str, help="Expected run_id to reject stale provenance.")
    parser.add_argument("--expected-project-id", type=str, help="Expected project_id to reject stale provenance.")
    parser.add_argument("--allow-silent", action="store_true", help="Allow silent video when mode/EDL has no speech/VO.")
    parser.add_argument("--allow-technical-release-profile", action="store_true", help="Deprecated alias for --gate-phase C1 --release-policy technical-smoke.")
    parser.add_argument("--out", type=Path, help="Optional POST_EXPORT_QA.json path.")
    args = parser.parse_args(argv)

    edl = json.loads(args.edl.read_text(encoding="utf-8")) if args.edl else None
    mcp_ev = json.loads(args.mcp_evidence.read_text(encoding="utf-8")) if args.mcp_evidence else None
    prev_checks = _load_preview_manifest(args.preview_manifest)
    percep_ev = json.loads(args.perceptual_evidence.read_text(encoding="utf-8")) if args.perceptual_evidence else None

    report = evaluate_export(
        args.mp4,
        edl=edl,
        require_audio=not args.allow_silent,
        preview_checks=prev_checks,
        mcp_export_evidence=mcp_ev,
        perceptual_audio_evidence=percep_ev,
        qa_level=args.qa_level,
        gate_phase=args.gate_phase,
        release_policy=args.release_policy,
        allow_technical_release_profile=args.allow_technical_release_profile,
        expected_run_id=args.expected_run_id,
        expected_project_id=args.expected_project_id,
    )
    if args.out:
        write_post_export_qa(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.qa_level == "release":
        if report["gate_phase"] == "C1" and report["release_policy"] == "technical-smoke":
            return 0 if report["technical_e2e_gate_pass"] else 1
        return 0 if report["creative_release_gate_pass"] else 1
    return 0 if report["mp4_qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
