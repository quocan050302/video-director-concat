#!/usr/bin/env python3
"""Validate editor-independent EDL against source inventory, rights, frame grid, claims, and mode."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

ALLOWED_RIGHTS = {"OWNED", "LICENSED", "GENERATED"}
BLOCKED_RIGHTS = {"ANALYSIS_ONLY", "UNKNOWN_RIGHTS"}
VALID_FRAMING_MODES = {"native", "framed", "blur_bg", "crop_tracked", "letterbox_intentional"}


def _parse_fps(fps_value: str | int | float) -> Fraction:
    if isinstance(fps_value, int):
        return Fraction(fps_value, 1)
    if isinstance(fps_value, float):
        return Fraction(str(fps_value))
    return Fraction(str(fps_value))


def _load_inventory_map(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if p.suffix.lower() == ".json":
        rows = json.loads(p.read_text(encoding="utf-8"))
    else:
        with open(p, "r", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    return {r["source_id"]: r for r in rows if r.get("source_id")}


def _load_ledger_map(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {r["asset_id"]: r for r in rows if r.get("asset_id")}


def validate_source_ranges(edl: dict[str, Any], inventory: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    fps = _parse_fps(edl.get("output_spec", {}).get("timeline_fps", "30/1"))

    for shot in edl.get("shots", []):
        sid = shot.get("shot_id", "<missing>")
        if sid in seen_ids:
            errors.append(f"DUPLICATE_SHOT_ID: {sid}")
        seen_ids.add(sid)

        src_id = shot.get("source_id")
        sin = shot.get("source_in_s")
        sout = shot.get("source_out_s")
        speed = float(shot.get("speed", 1.0))

        if sin is None or sout is None or sin < 0 or sout <= sin:
            errors.append(f"INVALID_SOURCE_RANGE: {sid} ({sin}..{sout})")
            continue
        if speed <= 0 or speed > 8.0:
            errors.append(f"INVALID_SPEED: {sid} speed={speed}")
            continue

        if src_id in inventory:
            src_meta = inventory[src_id]
            media_type = src_meta.get("media_type", "video")
            if media_type != "image":
                try:
                    dur = float(src_meta.get("duration_s", 0.0))
                except (TypeError, ValueError):
                    dur = 0.0
                if dur > 0 and sout > dur + 0.02:
                    errors.append(f"SOURCE_OUT_EXCEEDS_DURATION: {sid} source_out_s={sout} > duration_s={dur}")
        elif inventory:
            errors.append(f"UNKNOWN_SOURCE_ID: {sid} references {src_id} not in inventory")

        oin = shot.get("output_in_frame")
        oout = shot.get("output_out_frame")
        if isinstance(oin, int) and isinstance(oout, int) and oout > oin:
            expected_dur = float((oout - oin) / fps)
            actual_src_dur = (sout - sin) / speed
            if abs(expected_dur - actual_src_dur) > max(0.08, 2.0 / float(fps)):
                errors.append(
                    f"TIMING_SPEED_MISMATCH: {sid} timeline_dur={expected_dur:.3f}s vs source_dur/speed={actual_src_dur:.3f}s"
                )

    for ac in edl.get("audio_tracks", []):
        cid = ac.get("clip_id", "<audio>")
        sin = ac.get("source_in_s")
        sout = ac.get("source_out_s")
        if sin is None or sout is None or sin < 0 or sout <= sin:
            errors.append(f"INVALID_AUDIO_RANGE: {cid} ({sin}..{sout})")
            continue
        src_id = ac.get("source_id")
        if src_id in inventory:
            try:
                dur = float(inventory[src_id].get("duration_s", 0.0))
            except (TypeError, ValueError):
                dur = 0.0
            if dur > 0 and sout > dur + 0.02:
                errors.append(f"AUDIO_OUT_EXCEEDS_DURATION: {cid} source_out_s={sout} > duration_s={dur}")

    return errors


def validate_frame_grid(edl: dict[str, Any], output_fps: str | None = None) -> list[str]:
    errors: list[str] = []
    spec = edl.get("output_spec") or {}
    fps_str = output_fps or spec.get("timeline_fps")
    if not fps_str:
        return ["MISSING_TIMELINE_FPS"]
    try:
        fps = _parse_fps(fps_str)
        if fps <= 0:
            return [f"NON_POSITIVE_FPS: {fps_str}"]
    except (ValueError, ZeroDivisionError):
        return [f"INVALID_RATIONAL_FPS: {fps_str}"]

    for shot in edl.get("shots", []):
        sid = shot.get("shot_id", "<missing>")
        oin = shot.get("output_in_frame")
        oout = shot.get("output_out_frame")
        if not isinstance(oin, int) or not isinstance(oout, int) or isinstance(oin, bool) or isinstance(oout, bool):
            errors.append(f"NON_INTEGER_FRAME_BOUNDS: {sid}")
            continue
        if oin < 0 or oout <= oin:
            errors.append(f"INVALID_FRAME_ORDER: {sid} ({oin}..{oout})")
        shot_fps = shot.get("timeline_fps")
        if shot_fps and _parse_fps(shot_fps) != fps:
            errors.append(f"SHOT_FPS_MISMATCH: {sid} has {shot_fps}, expected {fps_str}")

    return errors


def validate_timeline_coverage(edl: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    shots = edl.get("shots", [])
    if not shots:
        return ["EMPTY_SHOT_LIST"]

    v1 = [s for s in shots if s.get("track", "V1") == "V1"]
    if not v1:
        return ["NO_V1_PRIMARY_SHOTS"]

    v1_sorted = sorted(v1, key=lambda s: (s.get("output_in_frame", 0), s.get("output_out_frame", 0)))
    if v1_sorted[0].get("output_in_frame", 0) != 0:
        errors.append(f"TIMELINE_START_GAP: first V1 shot starts at frame {v1_sorted[0].get('output_in_frame')}")

    for prev, cur in zip(v1_sorted, v1_sorted[1:]):
        p_out = prev.get("output_out_frame", 0)
        c_in = cur.get("output_in_frame", 0)
        if c_in > p_out:
            errors.append(f"TIMELINE_GAP: frames {p_out}..{c_in} between {prev.get('shot_id')} and {cur.get('shot_id')}")
        elif c_in < p_out:
            t_intent = str(cur.get("transition_intent", "")).lower()
            if not any(k in t_intent for k in ("dissolve", "crossfade", "overlap")):
                errors.append(f"UNINTENDED_OVERLAP: {prev.get('shot_id')} and {cur.get('shot_id')} overlap without dissolve intent")

    return errors


def validate_asset_rights(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]],
    license_ledger: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    ledger = license_ledger or {}

    def _check_item(label: str, src_id: str | None, declared_rights: str | None) -> None:
        inv_rights = (inventory.get(src_id or "", {}) or {}).get("rights_tag")
        effective_rights = inv_rights or declared_rights or "UNKNOWN_RIGHTS"
        if inv_rights and declared_rights and inv_rights != declared_rights:
            errors.append(f"RIGHTS_MISMATCH: {label} declares {declared_rights} but inventory has {inv_rights}")
        if effective_rights in BLOCKED_RIGHTS or effective_rights not in ALLOWED_RIGHTS:
            errors.append(f"FORBIDDEN_RIGHTS_IN_FINAL_EDL: {label} ({src_id}) has rights={effective_rights}")
        if effective_rights == "LICENSED":
            entry = ledger.get(src_id or "")
            if not entry:
                errors.append(f"MISSING_LICENSE_LEDGER_ENTRY: {label} ({src_id}) requires LICENSE_LEDGER.csv approval")
            elif entry.get("decision") != "APPROVED" or entry.get("commercial_use_allowed") != "YES":
                errors.append(f"UNAPPROVED_LICENSE_LEDGER_ENTRY: {label} ({src_id})")

    for shot in edl.get("shots", []):
        _check_item(shot.get("shot_id", "<shot>"), shot.get("source_id"), shot.get("source_rights"))
    for ac in edl.get("audio_tracks", []):
        _check_item(ac.get("clip_id", "<audio>"), ac.get("source_id"), ac.get("source_rights"))

    return errors


def validate_claim_evidence(edl: dict[str, Any], claims: list[dict[str, Any]] | None = None) -> list[str]:
    errors: list[str] = []
    claim_list = claims if claims is not None else edl.get("claims", [])
    claim_map = {c.get("claim_id"): c for c in claim_list if c.get("claim_id")}

    for cid, c in claim_map.items():
        if c.get("status") == "UNKNOWN_REMOVE":
            errors.append(f"UNVERIFIED_CLAIM_PRESENT: {cid} marked UNKNOWN_REMOVE must be deleted before EDL lock")

    for shot in edl.get("shots", []):
        for cid in shot.get("claim_evidence_ids", []):
            if cid not in claim_map:
                errors.append(f"DANGLING_CLAIM_REF: {shot.get('shot_id')} references missing claim {cid}")
            elif claim_map[cid].get("status") == "UNKNOWN_REMOVE":
                errors.append(f"SHOT_USES_REMOVED_CLAIM: {shot.get('shot_id')} -> {cid}")

    return errors


def validate_mode_constraints(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]] | None = None,
    brief: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    inv = inventory or {}
    caption_policy = (brief or {}).get("caption_policy") or edl.get("caption_policy", "OFF")
    spec = edl.get("output_spec") or {}
    out_w = int(spec.get("width", 0))
    out_h = int(spec.get("height", 0))

    if str(caption_policy).upper() == "OFF":
        for ov in edl.get("overlays", []):
            otype = str(ov.get("overlay_type", "")).lower()
            if otype in {"caption", "captions", "karaoke", "subtitle", "subtitles"}:
                errors.append(f"UNAUTHORIZED_CAPTION_OVERLAY: {ov.get('overlay_id')} while caption_policy=OFF")

    for shot in edl.get("shots", []):
        sid = shot.get("shot_id", "<shot>")
        safe = shot.get("safe_region_normalized")
        if safe is not None:
            if not (isinstance(safe, list) and len(safe) == 4 and 0.0 <= safe[0] < safe[2] <= 1.0 and 0.0 <= safe[1] < safe[3] <= 1.0):
                errors.append(f"INVALID_SAFE_REGION: {sid} -> {safe}")

        src = inv.get(shot.get("source_id", ""))
        if src and out_w > 0 and out_h > 0:
            try:
                sw = int(src.get("width", 0))
                sh = int(src.get("height", 0))
            except (TypeError, ValueError):
                sw, sh = 0, 0
            if sw > sh and out_h > out_w:
                fm = shot.get("framing_mode")
                if fm not in VALID_FRAMING_MODES or fm == "native":
                    errors.append(f"LANDSCAPE_IN_PORTRAIT_NEEDS_EXPLICIT_FRAMING: {sid} has framing_mode={fm}")

    return errors


def validate_all(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]] | None = None,
    license_ledger: dict[str, dict[str, Any]] | None = None,
    brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inv = inventory or {}
    checks = {
        "frame_grid": validate_frame_grid(edl),
        "source_ranges": validate_source_ranges(edl, inv),
        "timeline_coverage": validate_timeline_coverage(edl),
        "asset_rights": validate_asset_rights(edl, inv, license_ledger),
        "claim_evidence": validate_claim_evidence(edl),
        "mode_constraints": validate_mode_constraints(edl, inv, brief),
    }
    all_errors = [err for errs in checks.values() for err in errs]
    return {
        "status": "PASS_EDL_VALID" if not all_errors else "FAIL_EDL_INVALID",
        "error_count": len(all_errors),
        "checks": checks,
        "errors": all_errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate EDL JSON before Concat MCP execution.")
    parser.add_argument("--edl", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, help="Optional SOURCE_INVENTORY.csv or JSON.")
    parser.add_argument("--license-ledger", type=Path, help="Optional LICENSE_LEDGER.csv.")
    parser.add_argument("--out", type=Path, help="Optional validation JSON output.")
    args = parser.parse_args(argv)

    edl = json.loads(args.edl.read_text(encoding="utf-8"))
    inv = _load_inventory_map(args.inventory)
    ledger = _load_ledger_map(args.license_ledger)
    result = validate_all(edl, inv, ledger)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS_EDL_VALID" else 1


if __name__ == "__main__":
    sys.exit(main())
