#!/usr/bin/env python3
"""Fail-closed post-export QA for real Concat-exported MP4 files.

NEVER emits PASS on missing, empty, partial (.tmp), or corrupted MP4 files.
Always separates PASS_AUDIO_SIGNAL from PASS_AUDIO_PERCEPTUAL (PERCEPTUAL_AUDIO_PENDING).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


def _stream_sha256(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def probe_export(mp4: str | Path, timeout_s: int = 30) -> dict[str, Any]:
    """Validate real MP4 exists, is non-empty, not a .tmp artifact, and probes/decodes cleanly."""
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
    if duration_s <= 0:
        return {"status": "FAIL_EXPORT_DECODE", "error": "Export duration <= 0s"}

    # Bounded decode check via ffmpeg null muxer
    ffmpeg_bin = shutil.which("ffmpeg")
    decode_errors = ""
    if ffmpeg_bin:
        d_cmd = [ffmpeg_bin, "-v", "error", "-i", str(p), "-f", "null", "-"]
        try:
            d_proc = subprocess.run(d_cmd, capture_output=True, text=True, timeout=max(timeout_s, 60), check=False)
            if d_proc.returncode != 0 or d_proc.stderr.strip():
                decode_errors = (d_proc.stderr or f"exit={d_proc.returncode}").strip()[:400]
        except subprocess.TimeoutExpired:
            decode_errors = "ffmpeg decode check timed out"

    if decode_errors:
        return {"status": "FAIL_EXPORT_DECODE", "error": decode_errors}

    return {
        "status": "PASS_PROBE_AND_DECODE",
        "path": str(p),
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
    """Compare probed MP4 specs against target output_spec."""
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
        if shot.get(flag_key):
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
    timeout_s: int = 60,
) -> dict[str, Any]:
    """Run ffmpeg blackdetect/freezedetect and classify results against intentional EDL beats."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return {"status": "BLOCKED_ENV_FFMPEG_MISSING", "unintended_blacks": [], "unintended_freezes": []}

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
    for fs, fe in zip(starts, ends):
        rec = {"start_s": fs, "end_s": fe, "duration_s": round(fe - fs, 3)}
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
    timeout_s: int = 60,
) -> dict[str, Any]:
    """Measure real audio signal levels via ffmpeg volumedetect; never fakes perceptual approval."""
    probe = probe_export(mp4, timeout_s=min(timeout_s, 30))
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
        }

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return {
            "audio_signal_status": "BLOCKED_ENV_FFMPEG_MISSING",
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
        }

    cmd = [ffmpeg_bin, "-hide_banner", "-i", str(mp4), "-vn", "-af", "volumedetect", "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return {"audio_signal_status": "FAIL_AUDIO_TIMEOUT", "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING"}

    stderr = proc.stderr or ""
    m_mean = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", stderr)
    m_max = re.search(r"max_volume:\s*([-\d.]+)\s*dB", stderr)
    mean_db = float(m_mean.group(1)) if m_mean else None
    max_db = float(m_max.group(1)) if m_max else None

    if mean_db is None or max_db is None:
        sig_status = "FAIL_AUDIO_UNMEASURABLE"
    elif max_db >= -0.05:
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
        "cue_count_referenced": len(cue_sheet or []),
    }


def compare_preview_export_frame(
    preview_path: str | Path,
    mp4: str | Path,
    timestamp_s: float,
    timeout_s: int = 30,
) -> dict[str, Any]:
    """Compare a real Concat preview PNG against the exported MP4 frame at timestamp_s using ffmpeg PSNR."""
    prev = Path(preview_path)
    if not prev.exists() or prev.stat().st_size == 0:
        return {"status": "FAIL_PREVIEW_MISSING", "timestamp_s": timestamp_s}
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return {"status": "BLOCKED_ENV_FFMPEG_MISSING", "timestamp_s": timestamp_s}

    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-i", str(prev),
        "-ss", f"{max(0.0, timestamp_s):.3f}",
        "-i", str(mp4),
        "-frames:v", "1",
        "-lavfi", "[0:v][1:v]psnr",
        "-f", "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "FAIL_COMPARE_TIMEOUT", "timestamp_s": timestamp_s}

    m = re.search(r"average:([0-9.]+|inf)", proc.stderr or "")
    if not m:
        return {"status": "FAIL_PREVIEW_MISMATCH", "timestamp_s": timestamp_s, "detail": (proc.stderr or "")[-200:]}
    psnr_val = float("inf") if m.group(1) == "inf" else float(m.group(1))
    return {
        "status": "PASS_PREVIEW_MATCH" if psnr_val >= 20.0 else "FAIL_PREVIEW_MISMATCH",
        "timestamp_s": timestamp_s,
        "psnr_db": "inf" if psnr_val == float("inf") else round(psnr_val, 2),
    }


def write_post_export_qa(report: dict[str, Any], out_path: str | Path) -> None:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def evaluate_export(
    mp4: str | Path,
    edl: dict[str, Any] | None = None,
    require_audio: bool = True,
    preview_checks: list[tuple[str | Path, float]] | None = None,
    perceptual_audio_confirmed: bool = False,
) -> dict[str, Any]:
    probe = probe_export(mp4)
    if probe.get("status") != "PASS_PROBE_AND_DECODE":
        return {
            "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "overall_status": "FAIL_EXPORT_QA",
            "mp4_qa_pass": False,
            "audio_perceptual_status": "PERCEPTUAL_AUDIO_PENDING",
            "probe": probe,
        }

    spec = dict((edl or {}).get("output_spec") or {})
    if edl and edl.get("shots") and "expected_duration_s" not in spec:
        fps = float(Fraction(str(spec.get("timeline_fps", "30/1"))))
        max_frame = max(s["output_out_frame"] for s in edl["shots"])
        spec["expected_duration_s"] = round(max_frame / fps, 4)

    dim_check = verify_dimensions_fps_duration(probe, spec if spec else None)
    bf_check = detect_unintended_blacks_and_freezes(mp4, edl)
    audio_check = measure_audio_segments(mp4, require_audio=require_audio)
    if perceptual_audio_confirmed and audio_check["audio_signal_status"] == "PASS_AUDIO_SIGNAL":
        audio_check["audio_perceptual_status"] = "PASS_AUDIO_PERCEPTUAL"

    preview_results = [
        compare_preview_export_frame(p_img, mp4, t_s)
        for p_img, t_s in (preview_checks or [])
    ]

    technical_ok = (
        dim_check["status"] in {"PASS", "SKIPPED_NOT_APPLICABLE"}
        and bf_check["status"] == "PASS"
        and audio_check["audio_signal_status"] in {"PASS_AUDIO_SIGNAL", "SKIPPED_SILENT_MODE"}
        and all(pr["status"] == "PASS_PREVIEW_MATCH" for pr in preview_results)
    )

    if not technical_ok:
        overall = "FAIL_EXPORT_QA"
    elif audio_check["audio_perceptual_status"] == "PERCEPTUAL_AUDIO_PENDING":
        overall = "PASS_TECHNICAL_PENDING_PERCEPTUAL_AUDIO"
    else:
        overall = "PASS_END_TO_END_EXPORT_QA"

    return {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "overall_status": overall,
        "mp4_qa_pass": technical_ok,
        "audio_signal_status": audio_check["audio_signal_status"],
        "audio_perceptual_status": audio_check["audio_perceptual_status"],
        "probe": probe,
        "spec_check": dim_check,
        "black_freeze_check": bf_check,
        "audio_check": audio_check,
        "preview_comparisons": preview_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed post-export MP4 QA.")
    parser.add_argument("--mp4", type=Path, required=True, help="Actual Concat-exported MP4 file.")
    parser.add_argument("--edl", type=Path, help="Optional EDL JSON to check specs and intentional fades.")
    parser.add_argument("--allow-silent", action="store_true", help="Allow silent video when mode has no audio.")
    parser.add_argument("--out", type=Path, help="Optional POST_EXPORT_QA.json path.")
    args = parser.parse_args(argv)

    edl = json.loads(args.edl.read_text(encoding="utf-8")) if args.edl else None
    report = evaluate_export(args.mp4, edl=edl, require_audio=not args.allow_silent)
    if args.out:
        write_post_export_qa(report, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["mp4_qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
