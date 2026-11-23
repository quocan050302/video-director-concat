#!/usr/bin/env python3
"""Read-only source discovery, streaming SHA-256, ffprobe metadata, and bounded contact sheets.

Strictly read-only on all input paths. Never modifies, moves, or deletes originals.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
}

PROTECTED_ROOTS = {
    "/", "/System", "/Library", "/bin", "/sbin", "/usr", "/etc", "/private/etc",
    "C:\\", "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
}

INVENTORY_FIELDS = [
    "source_id",
    "relative_label",
    "media_type",
    "rights_tag",
    "bytes",
    "sha256",
    "duration_s",
    "width",
    "height",
    "r_frame_rate",
    "avg_frame_rate",
    "vfr_suspect",
    "rotation",
    "video_codec",
    "pix_fmt",
    "color_transfer",
    "has_audio",
    "audio_codec",
    "sample_rate",
    "channels",
    "probe_status",
    "notes",
]


def _is_protected_path(resolved: Path) -> bool:
    norm = str(resolved)
    if norm in PROTECTED_ROOTS:
        return True
    for root in ("/System", "/etc", "/private/etc", "/bin", "/sbin"):
        if norm == root or norm.startswith(root + "/"):
            return True
    return False


def _has_traversal_segments(raw_path: str) -> bool:
    parts = Path(raw_path).parts
    return ".." in parts


def discover_inputs(paths: list[str | Path], limits: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bounded, read-only file discovery with symlink escape and protected-path guards."""
    cfg = {
        "max_depth": 5,
        "max_files": 200,
        "max_file_gb": 8.0,
        "max_total_gb": 40.0,
        "allow_all_extensions": False,
    }
    if limits:
        cfg.update(limits)

    max_file_bytes = int(cfg["max_file_gb"] * (1024**3))
    max_total_bytes = int(cfg["max_total_gb"] * (1024**3))

    discovered: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_realpaths: set[str] = set()
    total_bytes = 0

    for raw in paths:
        raw_str = str(raw)
        if _has_traversal_segments(raw_str):
            rejected.append({"path": raw_str, "reason": "PATH_TRAVERSAL_REJECTED"})
            continue

        p = Path(raw_str)
        if not p.exists() and not p.is_symlink():
            rejected.append({"path": raw_str, "reason": "PATH_NOT_FOUND"})
            continue

        if p.is_symlink():
            rejected.append({"path": raw_str, "reason": "TOP_LEVEL_SYMLINK_REJECTED"})
            continue

        root_resolved = p.resolve()
        if _is_protected_path(root_resolved):
            rejected.append({"path": raw_str, "reason": "PROTECTED_SYSTEM_PATH_REJECTED"})
            continue

        if root_resolved.is_file():
            candidates = [(root_resolved, root_resolved.parent)]
        else:
            candidates = []
            root_depth = len(root_resolved.parts)
            for dirpath, dirnames, filenames in os.walk(root_resolved, followlinks=False):
                cur = Path(dirpath)
                depth = len(cur.parts) - root_depth
                if depth >= cfg["max_depth"]:
                    dirnames[:] = []
                # Prune symlinked directories
                safe_dirs = []
                for d in sorted(dirnames):
                    dp = cur / d
                    if dp.is_symlink():
                        rejected.append({"path": str(dp), "reason": "SYMLINK_DIR_REJECTED"})
                    else:
                        safe_dirs.append(d)
                dirnames[:] = safe_dirs

                for fname in sorted(filenames):
                    fp = cur / fname
                    if fp.is_symlink():
                        rejected.append({"path": str(fp), "reason": "SYMLINK_FILE_REJECTED"})
                        continue
                    try:
                        rfp = fp.resolve(strict=True)
                    except OSError as exc:
                        rejected.append({"path": str(fp), "reason": f"STAT_ERROR:{exc}"})
                        continue
                    # Symlink escape check
                    try:
                        rfp.relative_to(root_resolved)
                    except ValueError:
                        rejected.append({"path": str(fp), "reason": "SYMLINK_ESCAPE_REJECTED"})
                        continue
                    candidates.append((rfp, root_resolved))

        for file_path, base_root in candidates:
            if len(discovered) >= cfg["max_files"]:
                rejected.append({"path": str(file_path), "reason": "MAX_FILES_LIMIT_REACHED"})
                continue
            ext = file_path.suffix.lower()
            if not cfg["allow_all_extensions"] and ext not in MEDIA_EXTENSIONS:
                continue
            real_key = str(file_path)
            if real_key in seen_realpaths:
                continue
            try:
                size = file_path.stat().st_size
            except OSError as exc:
                rejected.append({"path": real_key, "reason": f"STAT_ERROR:{exc}"})
                continue
            if size > max_file_bytes:
                rejected.append({"path": real_key, "reason": "MAX_FILE_SIZE_EXCEEDED"})
                continue
            if total_bytes + size > max_total_bytes:
                rejected.append({"path": real_key, "reason": "MAX_TOTAL_SIZE_EXCEEDED"})
                continue

            seen_realpaths.add(real_key)
            total_bytes += size
            try:
                rel_label = str(file_path.relative_to(base_root))
            except ValueError:
                rel_label = file_path.name
            discovered.append(
                {
                    "abs_path": file_path,
                    "relative_label": rel_label,
                    "bytes": size,
                    "extension": ext,
                }
            )

    discovered.sort(key=lambda item: item["relative_label"])
    return discovered, rejected


def stream_sha256(path: str | Path, chunk_bytes: int = 1024 * 1024) -> str:
    """Compute SHA-256 via streaming binary chunks without loading whole media into RAM."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_bytes)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _parse_fps(rate_str: str | None) -> float | None:
    if not rate_str or rate_str in {"0/0", "N/A"}:
        return None
    try:
        return float(Fraction(rate_str))
    except (ValueError, ZeroDivisionError):
        return None


def probe_media(path: str | Path, timeout_s: int = 20) -> dict[str, Any]:
    """Run read-only ffprobe subprocess (argv array) and parse media stream metadata."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return {"probe_status": "FFPROBE_MISSING", "error": "ffprobe not found in PATH"}

    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return {"probe_status": "PROBE_TIMEOUT", "error": f"ffprobe exceeded {timeout_s}s"}
    except OSError as exc:
        return {"probe_status": "PROBE_OS_ERROR", "error": str(exc)}

    if proc.returncode != 0:
        return {
            "probe_status": "PROBE_FAILED",
            "error": (proc.stderr or proc.stdout).strip()[:400],
        }

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"probe_status": "PROBE_INVALID_JSON", "error": str(exc)}

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration_raw = fmt.get("duration") or (v_stream or {}).get("duration") or (a_stream or {}).get("duration")
    try:
        duration_s = round(float(duration_raw), 4) if duration_raw is not None else 0.0
    except (TypeError, ValueError):
        duration_s = 0.0

    r_fps_str = (v_stream or {}).get("r_frame_rate", "")
    avg_fps_str = (v_stream or {}).get("avg_frame_rate", "")
    r_fps = _parse_fps(r_fps_str)
    avg_fps = _parse_fps(avg_fps_str)
    vfr_suspect = False
    if r_fps and avg_fps and r_fps > 0:
        if abs(r_fps - avg_fps) / r_fps > 0.05:
            vfr_suspect = True

    rotation = 0
    if v_stream:
        tags = v_stream.get("tags") or {}
        if "rotate" in tags:
            try:
                rotation = int(tags["rotate"])
            except ValueError:
                rotation = 0
        for sd in v_stream.get("side_data_list") or []:
            if "rotation" in sd:
                try:
                    rotation = int(sd["rotation"])
                except (TypeError, ValueError):
                    pass

    ext = Path(path).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        media_type = "image"
    elif v_stream:
        media_type = "video"
    elif a_stream:
        media_type = "audio"
    else:
        media_type = "unknown"

    return {
        "probe_status": "OK",
        "media_type": media_type,
        "duration_s": duration_s,
        "width": int(v_stream["width"]) if v_stream and v_stream.get("width") else 0,
        "height": int(v_stream["height"]) if v_stream and v_stream.get("height") else 0,
        "r_frame_rate": r_fps_str,
        "avg_frame_rate": avg_fps_str,
        "vfr_suspect": vfr_suspect,
        "rotation": rotation,
        "video_codec": (v_stream or {}).get("codec_name", ""),
        "pix_fmt": (v_stream or {}).get("pix_fmt", ""),
        "color_transfer": (v_stream or {}).get("color_transfer", ""),
        "has_audio": a_stream is not None,
        "audio_codec": (a_stream or {}).get("codec_name", ""),
        "sample_rate": int(a_stream["sample_rate"]) if a_stream and a_stream.get("sample_rate") else 0,
        "channels": int(a_stream["channels"]) if a_stream and a_stream.get("channels") else 0,
    }


def sample_contact_sheet(
    path: str | Path,
    times: list[float],
    max_pixels: int = 640,
    out_dir: str | Path | None = None,
    timeout_s: int = 20,
) -> list[str]:
    """Extract bounded read-only sample stills at specified timestamps (never modifies source)."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin or not times or out_dir is None:
        return []
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    stem = Path(path).stem
    generated: list[str] = []
    scale_expr = f"scale='min({max_pixels},iw)':-2"

    for idx, t in enumerate(times[:12]):
        target = out_path / f"{stem}_t{idx:02d}_{t:.2f}s.jpg"
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", f"{max(0.0, float(t)):.3f}",
            "-i", str(path),
            "-frames:v", "1",
            "-vf", scale_expr,
            "-y",
            str(target),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
            if proc.returncode == 0 and target.exists() and target.stat().st_size > 0:
                generated.append(str(target))
        except (OSError, subprocess.SubprocessError):
            continue
    return generated


def write_inventory(records: list[dict[str, Any]], out_csv: str | Path, out_json: str | Path | None = None) -> None:
    """Write deterministic sorted SOURCE_INVENTORY.csv and optional JSON metadata."""
    ordered = sorted(records, key=lambda r: r.get("source_id", ""))
    csv_path = Path(out_csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        for rec in ordered:
            writer.writerow({k: rec.get(k, "") for k in INVENTORY_FIELDS})

    if out_json is not None:
        json_path = Path(out_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _probe_one(
    idx: int,
    item: dict[str, Any],
    rights_tag: str,
    timeout_s: int,
    contact_dir: Path | None,
) -> dict[str, Any]:
    abs_path: Path = item["abs_path"]
    sha = stream_sha256(abs_path)
    meta = probe_media(abs_path, timeout_s=timeout_s)
    source_id = f"U{idx:03d}"

    notes_parts = []
    if meta.get("error"):
        notes_parts.append(str(meta["error"]))
    if meta.get("vfr_suspect"):
        notes_parts.append("VFR_SUSPECT")
    if meta.get("color_transfer") in {"arib-std-b67", "smpte2084"}:
        notes_parts.append("HDR_INPUT")

    stills: list[str] = []
    if contact_dir is not None and meta.get("probe_status") == "OK" and meta.get("media_type") == "video":
        dur = float(meta.get("duration_s") or 0.0)
        if dur > 0:
            times = sorted({round(min(dur * frac, max(0.0, dur - 0.1)), 2) for frac in (0.1, 0.5, 0.85)})
            stills = sample_contact_sheet(abs_path, times, max_pixels=640, out_dir=contact_dir, timeout_s=timeout_s)

    return {
        "source_id": source_id,
        "relative_label": item["relative_label"],
        "media_type": meta.get("media_type", "unknown"),
        "rights_tag": rights_tag,
        "bytes": item["bytes"],
        "sha256": sha,
        "duration_s": meta.get("duration_s", 0.0),
        "width": meta.get("width", 0),
        "height": meta.get("height", 0),
        "r_frame_rate": meta.get("r_frame_rate", ""),
        "avg_frame_rate": meta.get("avg_frame_rate", ""),
        "vfr_suspect": meta.get("vfr_suspect", False),
        "rotation": meta.get("rotation", 0),
        "video_codec": meta.get("video_codec", ""),
        "pix_fmt": meta.get("pix_fmt", ""),
        "color_transfer": meta.get("color_transfer", ""),
        "has_audio": meta.get("has_audio", False),
        "audio_codec": meta.get("audio_codec", ""),
        "sample_rate": meta.get("sample_rate", 0),
        "channels": meta.get("channels", 0),
        "probe_status": meta.get("probe_status", "UNKNOWN"),
        "notes": "; ".join(notes_parts),
        "stills": stills,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded read-only media inventory probe.")
    parser.add_argument("inputs", nargs="+", help="Input files or folders (read-only).")
    parser.add_argument("--out-csv", type=Path, required=True, help="Output SOURCE_INVENTORY.csv path.")
    parser.add_argument("--out-json", type=Path, help="Optional JSON inventory path.")
    parser.add_argument("--contact-dir", type=Path, help="Optional directory for bounded sample stills.")
    parser.add_argument("--rights-tag", default="UNKNOWN_RIGHTS", choices=["OWNED", "LICENSED", "ANALYSIS_ONLY", "UNKNOWN_RIGHTS", "GENERATED"])
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--max-file-gb", type=float, default=8.0)
    parser.add_argument("--max-total-gb", type=float, default=40.0)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args(argv)

    limits = {
        "max_depth": args.max_depth,
        "max_files": args.max_files,
        "max_file_gb": args.max_file_gb,
        "max_total_gb": args.max_total_gb,
    }
    discovered, rejected = discover_inputs(args.inputs, limits=limits)
    worker_count = max(1, min(args.workers, 4))

    records: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        futs = [
            pool.submit(_probe_one, idx + 1, item, args.rights_tag, args.timeout, args.contact_dir)
            for idx, item in enumerate(discovered)
        ]
        for fut in futs:
            records.append(fut.result())

    write_inventory(records, args.out_csv, args.out_json)

    failed = [r for r in records if r["probe_status"] != "OK"]
    summary = {
        "status": "OK" if (records and not failed) else ("NO_MEDIA_FOUND" if not records else "PARTIAL_OR_FAILED"),
        "discovered_count": len(discovered),
        "probed_ok": len(records) - len(failed),
        "probed_failed": len(failed),
        "rejected": rejected,
        "out_csv": str(args.out_csv),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if (records and not failed) else 1


if __name__ == "__main__":
    sys.exit(main())
