#!/usr/bin/env python3
"""Fail-closed post-export QA for real Concat-exported MP4 files.

Strict separation of QA levels:
- technical: Standalone media diagnostic (probe, full decode, spec, black/freeze, audio signal).
  Returns PASS_TECHNICAL_ONLY at most; NEVER certifies Concat origin or end-to-end release readiness.
- release: End-to-end release gate. Requires:
  1. Valid MCP export provenance matching exact output path, allowed export root, SHA-256,
     export_wait completion, and save/close/reopen verification.
  2. Non-empty preview_checks with calibrated SSIM + PSNR + dimension checks.
  3. Full ffmpeg decode (ffmpeg missing => BLOCKED_ENV, never implicit PASS).
  4. Verified audio signal + structured perceptual audio evidence matching MP4 SHA-256
     (unless silent-by-design or explicit technical-release profile is declared).
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


def _stream_sha256(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


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


def _interval_covered(start: float, end: float, allowed: list[tuple[float, float]]) -> bool:
    for a_s, a_e in allowed:
        if start >= a_s - 0.15 and end <= a_e + 0.15:
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
    # Close trailing EOF freeze if freeze_start fired without freeze_end before end-of-stream
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


def measure_audio_segments(
    mp4: str | Path,
    cue_sheet: list[dict[str, Any]] | None = None,
    require_audio: bool = True,
    probe_data: dict[str, Any] | None = None,
    timeout_s: int = 60,
) -> dict[str, Any]:
    """Measure audio signal via volumedetect, ebur128 (LUFS/true peak), and silencedetect."""
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
        }

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return {
            "audio_signal_status": "BLOCKED_ENV_FFMPEG_MISSING",
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
        }

    # 1. volumedetect + silencedetect
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

    dropouts = []
    for m in re.finditer(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", stderr):
        dropouts.append({"end_s": float(m.group(1)), "duration_s": float(m.group(2))})

    # 2. Bounded EBU R128 integrated LUFS & true peak measurement
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
        sig_status = "FAIL_AUDIO_UNMEASURABLE"
    elif max_db >= -0.05 or (true_peak_dbfs is not None and true_peak_dbfs >= -0.05):
        sig_status = "FAIL_AUDIO_CLIP"
    elif mean_db <= -75.0:
        sig_status = "FAIL_AUDIO_SILENT"
    else:
        sig_status = "PASS_AUDIO_SIGNAL"

    return {
        "audio_signal_status": sig_status,
        "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
        "mean_volume_db": mean_db,
        "max_volume_db": max_db,
        "integrated_lufs": integrated_lufs,
        "true_peak_dbfs": true_peak_dbfs,
        "silence_dropouts": dropouts,
        "cue_count_referenced": len(cue_sheet or []),
    }


def _probe_image_dims(img_path: Path, timeout_s: int = 10) -> tuple[int, int] | None:
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None
    cmd = [
        ffprobe_bin, "-v", "error", "-print_format", "json",
        "-show_streams", str(img_path),
    ]
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
    """Compare real Concat preview image vs exported MP4 frame with dimension, SSIM, and PSNR checks."""
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

    # Align timestamp cleanly to rational frame grid if provided
    aligned_t = max(0.0, float(timestamp_s))
    if timeline_fps:
        try:
            fps = float(Fraction(str(timeline_fps)))
            if fps > 0:
                aligned_t = round(round(aligned_t * fps) / fps, 6)
        except (ValueError, ZeroDivisionError):
            pass

    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-i", str(prev),
        "-ss", f"{aligned_t:.6f}",
        "-i", str(mp4),
        "-frames:v", "1",
        "-lavfi", "[0:v]split=2[p1][p2];[1:v]split=2[e1][e2];[p1][e1]ssim;[p2][e2]psnr",
        "-f", "null",
        "-",
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
) -> dict[str, Any]:
    """Validate orchestrator-recorded Concat MCP export evidence against actual exported MP4."""
    if not mcp_evidence or not isinstance(mcp_evidence, dict):
        return {
            "status": "RELEASE_BLOCKED_NO_MCP_PROVENANCE",
            "errors": ["RELEASE_BLOCKED_NO_MCP_PROVENANCE: missing Concat MCP export evidence"],
            "trust_boundary": "Validates orchestrator-recorded MCP evidence consistency; self-supplied JSON is not external cryptographic attestation.",
        }

    errors: list[str] = []
    for req_field in ("project_id", "run_id", "concat_binary", "concat_version", "mcp_mode", "output_path", "sha256", "exported_at"):
        if not str(mcp_evidence.get(req_field) or "").strip():
            errors.append(f"MCP_PROVENANCE_MISSING_FIELD: {req_field}")

    if mcp_evidence.get("mcp_mode") not in {"headless", "window"}:
        errors.append(f"MCP_PROVENANCE_INVALID_MODE: {mcp_evidence.get('mcp_mode')!r}")

    ex_start = mcp_evidence.get("export_start") or {}
    ex_wait = mcp_evidence.get("export_wait") or {}
    if not isinstance(ex_start, dict) or not ex_start.get("job_id"):
        errors.append("MCP_PROVENANCE_MISSING_EXPORT_START_JOB_ID")
    if not isinstance(ex_wait, dict) or ex_wait.get("exit_ok") is not True or str(ex_wait.get("status", "")).lower() not in {"completed", "succeeded", "done"}:
        errors.append(f"MCP_PROVENANCE_EXPORT_WAIT_NOT_COMPLETED: {ex_wait!r}")
    elif ex_start.get("job_id") and ex_wait.get("job_id") and ex_start["job_id"] != ex_wait["job_id"]:
        errors.append("MCP_PROVENANCE_JOB_ID_MISMATCH")

    if mcp_evidence.get("reopen_verified") is not True or not str(mcp_evidence.get("timeline_fingerprint") or "").strip():
        errors.append("MCP_PROVENANCE_REOPEN_NOT_VERIFIED")

    actual_sha = str(probe_data.get("sha256") or "").lower()
    claimed_sha = str(mcp_evidence.get("sha256") or "").lower()
    if not SHA256_RE.match(claimed_sha) or claimed_sha != actual_sha:
        errors.append("MCP_PROVENANCE_SHA256_MISMATCH")

    actual_path = Path(probe_data.get("path", "")).resolve()
    claimed_path = Path(str(mcp_evidence.get("output_path") or "")).resolve()
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

    return {
        "status": "PASS_MCP_PROVENANCE_CONSISTENT" if not errors else "FAIL_MCP_PROVENANCE",
        "errors": errors,
        "trust_boundary": "Validates orchestrator-recorded MCP evidence consistency; self-supplied JSON is not external cryptographic attestation.",
    }


def validate_perceptual_audio_evidence(
    evidence: dict[str, Any] | None,
    actual_mp4_sha: str,
) -> str:
    if not evidence or not isinstance(evidence, dict):
        return "PERCEPTUAL_AUDIO_PENDING"
    reviewer = str(evidence.get("reviewer") or "").strip()
    reviewed_at = str(evidence.get("reviewed_at") or "").strip()
    sha = str(evidence.get("mp4_sha256") or "").strip().lower()
    verdict = str(evidence.get("verdict") or "").strip().upper()
    if reviewer and reviewed_at and sha == actual_mp4_sha.lower() and verdict == "PASS":
        return "PASS_AUDIO_PERCEPTUAL"
    if verdict == "FAIL":
        return "FAIL_AUDIO_PERCEPTUAL"
    return "PERCEPTUAL_AUDIO_PENDING"


def write_post_export_qa(report: dict[str, Any], out_path: str | Path) -> None:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evaluate_export(
    mp4: str | Path,
    edl: dict[str, Any] | None = None,
    require_audio: bool = True,
    preview_checks: list[tuple[str | Path, float]] | None = None,
    mcp_export_evidence: dict[str, Any] | None = None,
    perceptual_audio_evidence: dict[str, Any] | None = None,
    qa_level: str = "technical",
    allow_technical_release_profile: bool = False,
) -> dict[str, Any]:
    if qa_level not in {"technical", "release"}:
        raise ValueError(f"Unsupported qa_level: {qa_level!r}")

    probe = probe_export(mp4, require_full_decode=(qa_level == "release"))
    if probe.get("status") != "PASS_PROBE_AND_DECODE":
        return {
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "qa_level": qa_level,
            "overall_status": "FAIL_EXPORT_QA" if not str(probe.get("status", "")).startswith("BLOCKED") else probe["status"],
            "mp4_qa_pass": False,
            "release_gate_pass": False,
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
    audio_check = measure_audio_segments(mp4, require_audio=require_audio, probe_data=probe)

    if audio_check["audio_signal_status"] == "PASS_AUDIO_SIGNAL":
        audio_check["audio_perceptual_status"] = validate_perceptual_audio_evidence(
            perceptual_audio_evidence, probe["sha256"]
        )

    exp_dims = (probe["width"], probe["height"]) if probe.get("width") and probe.get("height") else None
    fps_hint = spec.get("timeline_fps") or probe.get("avg_frame_rate")
    preview_results = [
        compare_preview_export_frame(p_img, mp4, t_s, expected_dims=exp_dims, timeline_fps=fps_hint)
        for p_img, t_s in (preview_checks or [])
    ]

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
            "overall_status": "PASS_TECHNICAL_ONLY" if technical_ok else "FAIL_TECHNICAL_QA",
            "mp4_qa_pass": technical_ok,
            "release_gate_pass": False,
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

    # Strict release mode checks
    release_blockers: list[str] = []
    prov_check = validate_mcp_export_provenance(mcp_export_evidence, probe)
    if prov_check["status"] != "PASS_MCP_PROVENANCE_CONSISTENT":
        release_blockers.extend(prov_check["errors"])

    if not preview_results:
        release_blockers.append("PREVIEW_MISSING: release mode requires non-empty preview_checks")
    elif not all(pr["status"] == "PASS_PREVIEW_MATCH" for pr in preview_results):
        release_blockers.append("FAIL_PREVIEW_MISMATCH")

    if not technical_ok:
        release_blockers.append("FAIL_TECHNICAL_MEDIA_QA")

    percep = audio_check["audio_perceptual_status"]
    if require_audio and percep == "FAIL_AUDIO_PERCEPTUAL":
        release_blockers.append("FAIL_AUDIO_PERCEPTUAL")

    if release_blockers:
        overall = "FAIL_RELEASE_QA"
        release_pass = False
    elif require_audio and percep == "PERCEPTUAL_AUDIO_PENDING":
        if allow_technical_release_profile:
            overall = "C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING"
            release_pass = True
        else:
            overall = "PENDING_PERCEPTUAL_AUDIO"
            release_pass = False
            release_blockers.append("PERCEPTUAL_AUDIO_PENDING")
    else:
        overall = "PASS_END_TO_END_EXPORT_QA"
        release_pass = True

    return {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "qa_level": "release",
        "overall_status": overall,
        "mp4_qa_pass": technical_ok,
        "release_gate_pass": release_pass,
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


def _load_preview_manifest(path: Path | None) -> list[tuple[str, float]]:
    if not path:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("previews", data) if isinstance(data, dict) else data
    out: list[tuple[str, float]] = []
    for item in items:
        if isinstance(item, dict) and item.get("path") is not None and item.get("timestamp_s") is not None:
            out.append((str(item["path"]), float(item["timestamp_s"])))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed post-export MP4 QA (technical vs release).")
    parser.add_argument("--mp4", type=Path, required=True, help="Actual exported MP4 path.")
    parser.add_argument("--edl", type=Path, help="Optional EDL JSON for spec & intentional black/freeze checks.")
    parser.add_argument("--qa-level", choices=["technical", "release"], default="technical")
    parser.add_argument("--mcp-evidence", type=Path, help="MCP export provenance JSON (required for --qa-level release).")
    parser.add_argument("--preview-manifest", type=Path, help="Preview checks JSON list (required for --qa-level release).")
    parser.add_argument("--perceptual-evidence", type=Path, help="Optional structured human listening confirmation JSON.")
    parser.add_argument("--allow-silent", action="store_true", help="Allow silent video when mode has no audio.")
    parser.add_argument("--allow-technical-release-profile", action="store_true", help="Explicitly permit C1_TECHNICAL_E2E_PASS_PERCEPTUAL_PENDING.")
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
        allow_technical_release_profile=args.allow_technical_release_profile,
    )
    if args.out:
        write_post_export_qa(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.qa_level == "release":
        return 0 if report["release_gate_pass"] else 1
    return 0 if report["mp4_qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
