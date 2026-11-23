#!/usr/bin/env python3
"""Read-only source discovery, streaming SHA-256, ffprobe metadata, and bounded contact sheets.

True streaming os.scandir traversal (never materializes sorted(scandir) over unbounded directories)
enforcing max_files, max_total_gb, max_entries_scanned, max_dirs_scanned, max_wallclock_s, and
bounded rejected arrays. Explicitly flags incomplete scans (INCOMPLETE_SOURCE_INVENTORY, exit 2).
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
import time
import unicodedata
from collections import deque
from fractions import Fraction
from pathlib import Path
from typing import Any

MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
}

PROTECTED_EXACT_ROOTS = {
    "/", "/System", "/Library", "/Users", "/Volumes", "/bin", "/sbin", "/usr", "/etc", "/private/etc",
    "C:\\", "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)", "C:\\Users",
}

INCOMPLETE_REASON_PREFIXES = (
    "SCAN_BUDGET_REACHED:",
    "SCANDIR_ERROR:",
    "STAT_ERROR:",
    "PATH_NOT_FOUND",
    "PROTECTED_SYSTEM_PATH_REJECTED",
    "TOP_LEVEL_SYMLINK_REJECTED",
    "MAX_FILE_SIZE_EXCEEDED",
    "MAX_TOTAL_SIZE_EXCEEDED",
    "UNICODE_LABEL_COLLISION",
)

INVENTORY_FIELDS = [
    "source_id",
    "root_id",
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
    "vfr_detection_method",
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
    if norm in PROTECTED_EXACT_ROOTS:
        return True
    try:
        if resolved == Path.home().resolve():
            return True
    except OSError:
        pass
    for prefix in ("/System", "/etc", "/private/etc", "/bin", "/sbin"):
        if norm == prefix or norm.startswith(prefix + "/"):
            return True
    return False


def _has_traversal_segments(raw_path: str) -> bool:
    parts = [seg for seg in raw_path.replace("\\", "/").split("/") if seg]
    return ".." in parts


def discover_inputs_detailed(
    paths: list[str | Path],
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """True streaming, bounded, read-only file discovery with explicit completeness metadata."""
    cfg = {
        "max_depth": 5,
        "max_files": 200,
        "max_file_gb": 8.0,
        "max_total_gb": 40.0,
        "max_entries_scanned": 5000,
        "max_dirs_scanned": 1000,
        "max_wallclock_s": 30.0,
        "max_rejected": 200,
        "allow_all_extensions": False,
    }
    if limits:
        cfg.update(limits)

    max_file_bytes = int(cfg["max_file_gb"] * (1024**3))
    max_total_bytes = int(cfg["max_total_gb"] * (1024**3))
    max_files = int(cfg["max_files"])
    max_entries = int(cfg["max_entries_scanned"])
    max_dirs = int(cfg["max_dirs_scanned"])
    max_wallclock = float(cfg["max_wallclock_s"])
    max_rejected = int(cfg["max_rejected"])
    multi_root = len(paths) > 1

    start_t = time.monotonic()
    discovered: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    rejected_truncated_count = 0
    incomplete_reasons: list[str] = []
    seen_realpaths: set[str] = set()
    seen_labels: set[str] = set()
    total_bytes = 0
    entries_scanned = 0
    dirs_scanned = 0
    budget_stopped = False

    def _record_rejection(where: str, reason: str) -> None:
        nonlocal rejected_truncated_count
        if len(rejected) < max_rejected:
            rejected.append({"path": where, "reason": reason})
        else:
            rejected_truncated_count += 1
        if reason.startswith(INCOMPLETE_REASON_PREFIXES) and reason not in incomplete_reasons:
            incomplete_reasons.append(reason)

    def _check_budget(where: str) -> bool:
        nonlocal budget_stopped
        if len(discovered) >= max_files:
            _record_rejection(where, "SCAN_BUDGET_REACHED:MAX_FILES")
            budget_stopped = True
            return True
        if entries_scanned >= max_entries:
            _record_rejection(where, "SCAN_BUDGET_REACHED:MAX_ENTRIES")
            budget_stopped = True
            return True
        if dirs_scanned >= max_dirs:
            _record_rejection(where, "SCAN_BUDGET_REACHED:MAX_DIRS")
            budget_stopped = True
            return True
        if (time.monotonic() - start_t) >= max_wallclock:
            _record_rejection(where, "SCAN_BUDGET_REACHED:MAX_WALLCLOCK")
            budget_stopped = True
            return True
        return False

    def _consider_file(file_path: Path, base_root: Path, root_id: str) -> None:
        nonlocal total_bytes
        ext = file_path.suffix.lower()
        if not cfg["allow_all_extensions"] and ext not in MEDIA_EXTENSIONS:
            return
        real_key = str(file_path)
        if real_key in seen_realpaths:
            return
        try:
            size = file_path.stat().st_size
        except OSError as exc:
            _record_rejection(real_key, f"STAT_ERROR:{exc}")
            return
        if size > max_file_bytes:
            _record_rejection(real_key, "MAX_FILE_SIZE_EXCEEDED")
            return
        if total_bytes + size > max_total_bytes:
            _record_rejection(real_key, "MAX_TOTAL_SIZE_EXCEEDED")
            return
        try:
            rel_inner = file_path.relative_to(base_root).as_posix()
        except ValueError:
            rel_inner = file_path.name
        rel_norm = unicodedata.normalize("NFC", rel_inner)
        rel_label = f"{root_id}/{rel_norm}" if multi_root else rel_norm
        if rel_label in seen_labels:
            _record_rejection(real_key, f"UNICODE_LABEL_COLLISION:{rel_label}")
            return
        seen_realpaths.add(real_key)
        seen_labels.add(rel_label)
        total_bytes += size
        discovered.append(
            {
                "abs_path": file_path,
                "root_id": root_id,
                "root_path": base_root,
                "relative_label": rel_label,
                "bytes": size,
                "extension": ext,
            }
        )

    for root_idx, raw in enumerate(paths, start=1):
        if budget_stopped:
            break
        root_id = f"R{root_idx:02d}"
        raw_str = str(raw)
        if _has_traversal_segments(raw_str):
            _record_rejection(raw_str, "PATH_TRAVERSAL_REJECTED")
            continue

        p = Path(raw_str)
        if not p.exists() and not p.is_symlink():
            _record_rejection(raw_str, "PATH_NOT_FOUND")
            continue
        if p.is_symlink():
            _record_rejection(raw_str, "TOP_LEVEL_SYMLINK_REJECTED")
            continue

        root_resolved = p.resolve()
        if _is_protected_path(root_resolved):
            _record_rejection(raw_str, "PROTECTED_SYSTEM_PATH_REJECTED")
            continue

        if root_resolved.is_file():
            if not _check_budget(str(root_resolved)):
                entries_scanned += 1
                _consider_file(root_resolved, root_resolved.parent, root_id)
            continue

        queue: deque[tuple[Path, int]] = deque([(root_resolved, 0)])
        while queue and not budget_stopped:
            cur_dir, depth = queue.popleft()
            if dirs_scanned >= max_dirs:
                _record_rejection(str(cur_dir), "SCAN_BUDGET_REACHED:MAX_DIRS")
                budget_stopped = True
                break
            dirs_scanned += 1

            child_dirs: list[Path] = []
            try:
                with os.scandir(cur_dir) as it:
                    # TRUE streaming iteration: NEVER sort or materialize unbounded directory!
                    for entry in it:
                        if _check_budget(entry.path):
                            break
                        entries_scanned += 1
                        ep = Path(entry.path)
                        try:
                            if entry.is_symlink():
                                reason = "SYMLINK_DIR_REJECTED" if entry.is_dir(follow_symlinks=True) else "SYMLINK_FILE_REJECTED"
                                _record_rejection(entry.path, reason)
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if depth < int(cfg["max_depth"]):
                                    child_dirs.append(ep)
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            rfp = ep.resolve(strict=True)
                        except OSError as exc:
                            _record_rejection(entry.path, f"STAT_ERROR:{exc}")
                            continue

                        try:
                            rfp.relative_to(root_resolved)
                        except ValueError:
                            _record_rejection(entry.path, "SYMLINK_ESCAPE_REJECTED")
                            continue

                        _consider_file(rfp, root_resolved, root_id)
            except OSError as exc:
                _record_rejection(str(cur_dir), f"SCANDIR_ERROR:{exc}")
                continue

            # Deterministic ordering of the bounded child dirs collected within budget
            for cd in sorted(child_dirs, key=lambda d: d.name):
                queue.append((cd, depth + 1))

    # Deterministic lexical sort ONLY over the bounded collected set
    discovered.sort(key=lambda item: (item["root_id"], item["relative_label"]))
    scan_complete = (not budget_stopped) and (len(incomplete_reasons) == 0)
    return {
        "discovered": discovered,
        "rejected": rejected,
        "rejected_truncated_count": rejected_truncated_count,
        "scan_complete": scan_complete,
        "incomplete_reasons": incomplete_reasons,
        "entries_scanned": entries_scanned,
        "dirs_scanned": dirs_scanned,
    }


def discover_inputs(
    paths: list[str | Path],
    limits: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Backwards-compatible wrapper returning (discovered, rejected)."""
    res = discover_inputs_detailed(paths, limits=limits)
    return res["discovered"], res["rejected"]


def stream_sha256(path: str | Path, chunk_bytes: int = 1024 * 1024) -> str:
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
        return {"probe_status": "PROBE_FAILED", "error": (proc.stderr or proc.stdout).strip()[:400]}

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
    vfr_suspect = bool(r_fps and avg_fps and r_fps > 0 and abs(r_fps - avg_fps) / r_fps > 0.05)

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
        "vfr_detection_method": "header_rate_heuristic_non_definitive" if v_stream else "n/a",
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
    source_id: str = "SRC",
    sha_prefix: str = "",
    timeout_s: int = 20,
) -> list[str]:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin or not times or out_dir is None:
        return []
    out_path = Path(out_dir).resolve()
    out_path.mkdir(parents=True, exist_ok=True)
    safe_prefix = f"{source_id}_{sha_prefix[:8]}" if sha_prefix else source_id
    generated: list[str] = []
    scale_expr = f"scale='min({max_pixels},iw)':-2"

    for idx, t in enumerate(times[:6]):
        target = out_path / f"{safe_prefix}_t{idx:02d}_{t:.2f}s.jpg"
        cmd = [
            ffmpeg_bin, "-hide_banner", "-loglevel", "error",
            "-ss", f"{max(0.0, float(t)):.3f}",
            "-i", str(path), "-frames:v", "1", "-vf", scale_expr, "-y", str(target),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
            if proc.returncode == 0 and target.exists() and target.stat().st_size > 0:
                generated.append(str(target))
        except (OSError, subprocess.SubprocessError):
            continue
    return generated


def write_inventory(records: list[dict[str, Any]], out_csv: str | Path, out_json: str | Path | None = None) -> None:
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
        notes_parts.append("VFR_SUSPECT_HEURISTIC")
    if meta.get("color_transfer") in {"arib-std-b67", "smpte2084"}:
        notes_parts.append("HDR_INPUT")

    stills: list[str] = []
    if contact_dir is not None and meta.get("probe_status") == "OK" and meta.get("media_type") == "video":
        dur = float(meta.get("duration_s") or 0.0)
        if dur > 0:
            times = sorted({round(min(dur * frac, max(0.0, dur - 0.1)), 2) for frac in (0.1, 0.5, 0.85)})
            stills = sample_contact_sheet(
                abs_path, times, max_pixels=640, out_dir=contact_dir,
                source_id=source_id, sha_prefix=sha[:8], timeout_s=timeout_s,
            )

    return {
        "source_id": source_id,
        "root_id": item.get("root_id", "R01"),
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
        "vfr_detection_method": meta.get("vfr_detection_method", "n/a"),
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
    parser = argparse.ArgumentParser(description="Bounded streaming read-only media inventory probe.")
    parser.add_argument("inputs", nargs="+", help="Input files or folders (read-only).")
    parser.add_argument("--out-csv", type=Path, required=True, help="Output SOURCE_INVENTORY.csv path.")
    parser.add_argument("--out-json", type=Path, help="Optional JSON inventory path.")
    parser.add_argument("--contact-dir", type=Path, help="Optional directory for bounded sample stills.")
    parser.add_argument("--rights-tag", default="UNKNOWN_RIGHTS", choices=["OWNED", "LICENSED", "ANALYSIS_ONLY", "UNKNOWN_RIGHTS", "GENERATED"])
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--max-file-gb", type=float, default=8.0)
    parser.add_argument("--max-total-gb", type=float, default=40.0)
    parser.add_argument("--max-entries", type=int, default=5000)
    parser.add_argument("--max-dirs", type=int, default=1000)
    parser.add_argument("--max-wallclock", type=float, default=30.0)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--allow-partial-inventory", action="store_true", help="Inspection-only flag; still never marks status OK when incomplete.")
    args = parser.parse_args(argv)

    limits = {
        "max_depth": args.max_depth,
        "max_files": args.max_files,
        "max_file_gb": args.max_file_gb,
        "max_total_gb": args.max_total_gb,
        "max_entries_scanned": args.max_entries,
        "max_dirs_scanned": args.max_dirs,
        "max_wallclock_s": args.max_wallclock,
    }
    scan = discover_inputs_detailed(args.inputs, limits=limits)
    discovered = scan["discovered"]
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
    scan_complete = scan["scan_complete"]
    if not records:
        status = "INCOMPLETE_SOURCE_INVENTORY" if not scan_complete else "NO_MEDIA_FOUND"
        exit_code = 2 if not scan_complete else 1
    elif failed:
        status = "PARTIAL_OR_FAILED"
        exit_code = 1
    elif not scan_complete:
        status = "PARTIAL_INVENTORY_APPROVED_FOR_INSPECTION_ONLY" if args.allow_partial_inventory else "INCOMPLETE_SOURCE_INVENTORY"
        exit_code = 0 if args.allow_partial_inventory else 2
    else:
        status = "OK"
        exit_code = 0

    summary = {
        "status": status,
        "scan_complete": scan_complete,
        "incomplete_reasons": scan["incomplete_reasons"],
        "entries_scanned": scan["entries_scanned"],
        "dirs_scanned": scan["dirs_scanned"],
        "discovered_count": len(discovered),
        "probed_ok": len(records) - len(failed),
        "probed_failed": len(failed),
        "rejected": scan["rejected"],
        "rejected_truncated_count": scan["rejected_truncated_count"],
        "out_csv": str(args.out_csv),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
