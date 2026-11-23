#!/usr/bin/env python3
"""Fail-closed EDL validator against verified source inventory, rights, claims, frame grid, and mode.

Supports two explicit validation modes:
- release (default): FAIL-CLOSED. Requires verified source inventory, probe_status=OK, valid SHA-256,
  inventory-authoritative rights (OWNED/LICENSED/GENERATED only), complete LICENSED ledger evidence,
  GENERATED model/weight/voice provenance, and evidence-backed claim citations.
  Returns PASS_EDL_VALID_FOR_RELEASE only when every release gate passes.
- draft: Planning-only check without full inventory; still enforces frame grid, timing, and blocks
  ANALYSIS_ONLY / UNKNOWN_RIGHTS / UNKNOWN_REMOVE. Returns PASS_EDL_DRAFT_ONLY (never release green).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

ALLOWED_RIGHTS = {"OWNED", "LICENSED", "GENERATED"}
BLOCKED_RIGHTS = {"ANALYSIS_ONLY", "UNKNOWN_RIGHTS"}
VALID_FRAMING_MODES = {"native", "framed", "blur_bg", "crop_tracked", "letterbox_intentional"}
VALID_CLAIM_STATUSES = {"VERIFIED_WITH_EVIDENCE", "PLAUSIBLE_NOT_ADVERTISABLE", "UNKNOWN_REMOVE"}
COMMERCIAL_MODES = {"product_ad", "conversion_ad", "product_review", "affiliate"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
STRONG_COMMERCIAL_CLAIM_RE = re.compile(
    r"(\d+\s*[%xX]|[$€£]\s*\d+|guarantee[sd]?|proven|#1|\bfree\b|\b100%\b|\bsave\s+\d+)",
    re.IGNORECASE,
)


def _is_finite_number(val: Any) -> bool:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return False
    return math.isfinite(float(val))


def _is_strict_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _parse_fps(fps_value: Any) -> Fraction:
    if isinstance(fps_value, bool) or fps_value is None:
        raise ValueError(f"Invalid FPS type: {type(fps_value).__name__}")
    if isinstance(fps_value, int):
        return Fraction(fps_value, 1)
    if isinstance(fps_value, float):
        if not math.isfinite(fps_value):
            raise ValueError(f"Non-finite FPS: {fps_value}")
        return Fraction(str(fps_value))
    if isinstance(fps_value, str):
        s = fps_value.strip()
        if not s or s.lower() in {"nan", "inf", "-inf", "infinity", "-infinity"}:
            raise ValueError(f"Non-finite FPS string: {fps_value!r}")
        return Fraction(s)
    raise ValueError(f"Unsupported FPS value: {fps_value!r}")


def _is_safe_relative_label(label: str) -> bool:
    if not label or not isinstance(label, str):
        return False
    if "\x00" in label:
        return False
    p = Path(label)
    if p.is_absolute():
        return False
    if ".." in p.parts:
        return False
    if re.match(r"^[A-Za-z]:[\\/]", label):
        return False
    return True


def _load_inventory_map(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    if p.suffix.lower() == ".json":
        rows = json.loads(p.read_text(encoding="utf-8"))
    else:
        with open(p, "r", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    return {r["source_id"]: r for r in rows if isinstance(r, dict) and r.get("source_id")}


def _load_ledger_map(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = (r.get("asset_id") or r.get("source_id") or "").strip()
        if key:
            out[key] = r
    return out


def validate_frame_grid(edl: dict[str, Any], output_fps: Any = None) -> list[str]:
    errors: list[str] = []
    spec = edl.get("output_spec") or {}
    fps_raw = output_fps if output_fps is not None else spec.get("timeline_fps")
    if fps_raw is None or fps_raw == "":
        return ["MISSING_TIMELINE_FPS"]
    try:
        fps = _parse_fps(fps_raw)
        if fps <= 0:
            return [f"NON_POSITIVE_FPS: {fps_raw}"]
    except (ValueError, ZeroDivisionError):
        return [f"INVALID_RATIONAL_FPS: {fps_raw}"]

    w = spec.get("width")
    h = spec.get("height")
    if w is not None and (not _is_strict_int(w) or w <= 0):
        errors.append(f"INVALID_OUTPUT_WIDTH: {w!r}")
    if h is not None and (not _is_strict_int(h) or h <= 0):
        errors.append(f"INVALID_OUTPUT_HEIGHT: {h!r}")

    for shot in edl.get("shots", []):
        if not isinstance(shot, dict):
            errors.append("INVALID_SHOT_RECORD_TYPE")
            continue
        sid = shot.get("shot_id", "<missing>")
        oin = shot.get("output_in_frame")
        oout = shot.get("output_out_frame")
        if not _is_strict_int(oin) or not _is_strict_int(oout):
            errors.append(f"NON_INTEGER_FRAME_BOUNDS: {sid}")
            continue
        if oin < 0 or oout <= oin:
            errors.append(f"INVALID_FRAME_ORDER: {sid} ({oin}..{oout})")
        shot_fps = shot.get("timeline_fps")
        if shot_fps is not None:
            try:
                if _parse_fps(shot_fps) != fps:
                    errors.append(f"SHOT_FPS_MISMATCH: {sid} has {shot_fps}, expected {fps_raw}")
            except (ValueError, ZeroDivisionError):
                errors.append(f"INVALID_SHOT_FPS: {sid} -> {shot_fps!r}")

    for ac in edl.get("audio_tracks", []):
        if not isinstance(ac, dict):
            errors.append("INVALID_AUDIO_RECORD_TYPE")
            continue
        cid = ac.get("clip_id", "<audio>")
        oin = ac.get("output_in_frame")
        oout = ac.get("output_out_frame")
        if oin is not None or oout is not None:
            if not _is_strict_int(oin) or not _is_strict_int(oout) or oin < 0 or oout <= oin:
                errors.append(f"INVALID_AUDIO_FRAME_BOUNDS: {cid} ({oin}..{oout})")

    return errors


def validate_source_ranges(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]],
    validation_mode: str = "release",
) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    try:
        fps = _parse_fps((edl.get("output_spec") or {}).get("timeline_fps", "30/1"))
        if fps <= 0:
            fps = Fraction(30, 1)
    except (ValueError, ZeroDivisionError):
        fps = Fraction(30, 1)

    for shot in edl.get("shots", []):
        if not isinstance(shot, dict):
            errors.append("INVALID_SHOT_RECORD_TYPE")
            continue
        sid = shot.get("shot_id", "<missing>")
        if not isinstance(sid, str) or not sid.strip():
            errors.append(f"INVALID_SHOT_ID: {sid!r}")
            continue
        if sid in seen_ids:
            errors.append(f"DUPLICATE_SHOT_ID: {sid}")
        seen_ids.add(sid)

        src_id = shot.get("source_id")
        if not isinstance(src_id, str) or not src_id.strip():
            errors.append(f"INVALID_SOURCE_ID_TYPE: {sid} -> {src_id!r}")
            continue

        sin = shot.get("source_in_s")
        sout = shot.get("source_out_s")
        speed_raw = shot.get("speed", 1.0)

        if not _is_finite_number(sin) or not _is_finite_number(sout) or float(sin) < 0.0 or float(sout) <= float(sin):
            errors.append(f"INVALID_SOURCE_RANGE: {sid} ({sin!r}..{sout!r})")
            continue
        if not _is_finite_number(speed_raw) or float(speed_raw) <= 0.0 or float(speed_raw) > 8.0:
            errors.append(f"INVALID_SPEED: {sid} speed={speed_raw!r}")
            continue

        sin_f = float(sin)
        sout_f = float(sout)
        speed = float(speed_raw)

        if src_id in inventory:
            src_meta = inventory[src_id]
            media_type = str(src_meta.get("media_type", "video")).lower()
            if media_type == "audio":
                errors.append(f"AUDIO_USED_AS_VIDEO_SHOT: {sid} references audio source {src_id}")
            elif media_type != "image":
                try:
                    dur = float(src_meta.get("duration_s", 0.0))
                except (TypeError, ValueError):
                    dur = -1.0
                if not math.isfinite(dur) or dur <= 0.0:
                    errors.append(f"INVALID_SOURCE_DURATION: {sid} ({src_id}) duration_s={src_meta.get('duration_s')!r}")
                elif sout_f > dur + 0.02:
                    errors.append(f"SOURCE_OUT_EXCEEDS_DURATION: {sid} source_out_s={sout_f} > duration_s={dur}")
        elif validation_mode == "release" or inventory:
            errors.append(f"SOURCE_ID_NOT_IN_INVENTORY: {sid} references {src_id}")

        oin = shot.get("output_in_frame")
        oout = shot.get("output_out_frame")
        if _is_strict_int(oin) and _is_strict_int(oout) and oout > oin:
            expected_dur = float((oout - oin) / fps)
            actual_src_dur = (sout_f - sin_f) / speed
            if abs(expected_dur - actual_src_dur) > max(0.08, 2.0 / float(fps)):
                errors.append(
                    f"TIMING_SPEED_MISMATCH: {sid} timeline_dur={expected_dur:.3f}s vs source_dur/speed={actual_src_dur:.3f}s"
                )

    for ac in edl.get("audio_tracks", []):
        if not isinstance(ac, dict):
            errors.append("INVALID_AUDIO_RECORD_TYPE")
            continue
        cid = ac.get("clip_id", "<audio>")
        src_id = ac.get("source_id")
        if not isinstance(src_id, str) or not src_id.strip():
            errors.append(f"INVALID_AUDIO_SOURCE_ID: {cid}")
            continue
        sin = ac.get("source_in_s")
        sout = ac.get("source_out_s")
        if not _is_finite_number(sin) or not _is_finite_number(sout) or float(sin) < 0.0 or float(sout) <= float(sin):
            errors.append(f"INVALID_AUDIO_RANGE: {cid} ({sin!r}..{sout!r})")
            continue
        if src_id in inventory:
            try:
                dur = float(inventory[src_id].get("duration_s", 0.0))
            except (TypeError, ValueError):
                dur = -1.0
            if not math.isfinite(dur) or dur <= 0.0:
                errors.append(f"INVALID_AUDIO_SOURCE_DURATION: {cid} ({src_id})")
            elif float(sout) > dur + 0.02:
                errors.append(f"AUDIO_OUT_EXCEEDS_DURATION: {cid} source_out_s={sout} > duration_s={dur}")
        elif validation_mode == "release" or inventory:
            errors.append(f"SOURCE_ID_NOT_IN_INVENTORY: {cid} references {src_id}")

    return errors


def validate_timeline_coverage(edl: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    shots = [s for s in edl.get("shots", []) if isinstance(s, dict)]
    if not shots:
        return ["EMPTY_SHOT_LIST"]

    v1 = [s for s in shots if s.get("track", "V1") == "V1"]
    if not v1:
        return ["NO_V1_PRIMARY_SHOTS"]

    valid_v1 = [s for s in v1 if _is_strict_int(s.get("output_in_frame")) and _is_strict_int(s.get("output_out_frame"))]
    if len(valid_v1) != len(v1):
        return ["TIMELINE_COVERAGE_SKIPPED_DUE_TO_INVALID_FRAME_BOUNDS"]

    v1_sorted = sorted(valid_v1, key=lambda s: (s["output_in_frame"], s["output_out_frame"]))
    if v1_sorted[0]["output_in_frame"] != 0:
        errors.append(f"TIMELINE_START_GAP: first V1 shot starts at frame {v1_sorted[0]['output_in_frame']}")

    for prev, cur in zip(v1_sorted, v1_sorted[1:]):
        p_out = prev["output_out_frame"]
        c_in = cur["output_in_frame"]
        if c_in > p_out:
            errors.append(f"TIMELINE_GAP: frames {p_out}..{c_in} between {prev.get('shot_id')} and {cur.get('shot_id')}")
        elif c_in < p_out:
            t_intent = str(cur.get("transition_intent", "")).lower()
            if not any(k in t_intent for k in ("dissolve", "crossfade", "overlap")):
                errors.append(f"UNINTENDED_OVERLAP: {prev.get('shot_id')} and {cur.get('shot_id')} overlap without dissolve intent")

    total_v1_end = max(s["output_out_frame"] for s in v1_sorted)

    # Secondary visual tracks (V2, V3...) may legitimately overlap V1, but must stay within [0, total_v1_end]
    for s in shots:
        if s.get("track", "V1") == "V1":
            continue
        oin, oout = s.get("output_in_frame"), s.get("output_out_frame")
        if _is_strict_int(oin) and _is_strict_int(oout):
            if oout > total_v1_end:
                errors.append(f"OVERLAY_SHOT_EXCEEDS_V1_END: {s.get('shot_id')} ends at {oout} > V1 end {total_v1_end}")

    for ov in edl.get("overlays", []):
        if not isinstance(ov, dict):
            continue
        oin, oout = ov.get("output_in_frame"), ov.get("output_out_frame")
        if oin is not None and oout is not None:
            if not _is_strict_int(oin) or not _is_strict_int(oout) or oin < 0 or oout <= oin:
                errors.append(f"INVALID_OVERLAY_FRAME_BOUNDS: {ov.get('overlay_id')}")
            elif oout > total_v1_end:
                errors.append(f"OVERLAY_EXCEEDS_TIMELINE_END: {ov.get('overlay_id')} ({oout} > {total_v1_end})")

    return errors


def validate_asset_rights(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]],
    license_ledger: dict[str, dict[str, Any]] | None = None,
    run_dir: str | Path | None = None,
    validation_mode: str = "release",
) -> list[str]:
    errors: list[str] = []
    ledger = license_ledger or {}

    if validation_mode == "release" and not inventory:
        return ["MISSING_SOURCE_INVENTORY: release validation requires an independently probed SOURCE_INVENTORY"]

    def _check_ledger_evidence(label: str, src_id: str, entry: dict[str, Any], is_generated: bool) -> None:
        if entry.get("decision") != "APPROVED" or entry.get("commercial_use_allowed") != "YES":
            errors.append(f"UNVERIFIED_LICENSE: {label} ({src_id}) ledger decision/commercial_use not APPROVED+YES")
            return
        lic_url = str(entry.get("license_url") or "").strip()
        lic_ev = str(entry.get("license_evidence_path") or "").strip()
        lic_name = str(entry.get("license_name") or "").strip()
        if not lic_url and not lic_ev:
            errors.append(f"MISSING_LICENSE_EVIDENCE: {label} ({src_id}) requires license_url or license_evidence_path")
        if is_generated and not lic_name:
            errors.append(f"MISSING_GENERATED_PROVENANCE: {label} ({src_id}) requires code/model/voice license_name")
        if lic_ev:
            if not _is_safe_relative_label(lic_ev):
                errors.append(f"UNSAFE_LICENSE_EVIDENCE_PATH: {label} ({src_id}) -> {lic_ev}")
            elif run_dir is not None:
                root = Path(run_dir).resolve()
                target = (root / lic_ev).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    errors.append(f"UNSAFE_LICENSE_EVIDENCE_PATH: {label} ({src_id}) escapes run_dir")
                else:
                    if not target.exists():
                        errors.append(f"LICENSE_EVIDENCE_FILE_NOT_FOUND: {label} ({src_id}) -> {lic_ev}")

    def _check_item(label: str, src_id: Any, declared_rights: Any) -> None:
        if not isinstance(src_id, str) or not src_id.strip():
            errors.append(f"INVALID_SOURCE_ID: {label}")
            return

        if validation_mode == "release":
            if src_id not in inventory:
                errors.append(f"SOURCE_ID_NOT_IN_INVENTORY: {label} ({src_id})")
                return
            src_meta = inventory[src_id]
            probe_st = str(src_meta.get("probe_status") or "").strip()
            if probe_st != "OK":
                errors.append(f"SOURCE_PROBE_NOT_OK: {label} ({src_id}) probe_status={probe_st!r}")
            sha = str(src_meta.get("sha256") or "").strip()
            if not SHA256_RE.match(sha):
                errors.append(f"INVALID_SOURCE_SHA256: {label} ({src_id}) sha256={sha!r}")
            rel_label = str(src_meta.get("relative_label") or "").strip()
            if not _is_safe_relative_label(rel_label):
                errors.append(f"UNSAFE_SOURCE_LABEL: {label} ({src_id}) relative_label={rel_label!r}")

            inv_rights = str(src_meta.get("rights_tag") or "").strip()
            if not inv_rights:
                errors.append(f"MISSING_INVENTORY_RIGHTS_TAG: {label} ({src_id})")
                return
            if declared_rights and str(declared_rights).strip() != inv_rights:
                errors.append(f"SOURCE_RIGHTS_MISMATCH: {label} ({src_id}) EDL={declared_rights} vs inventory={inv_rights}")
            effective_rights = inv_rights
        else:
            # Draft mode: still enforce inventory truth if present; never allow blocked rights
            inv_rights = str((inventory.get(src_id) or {}).get("rights_tag") or "").strip()
            if inv_rights and declared_rights and str(declared_rights).strip() != inv_rights:
                errors.append(f"SOURCE_RIGHTS_MISMATCH: {label} ({src_id}) EDL={declared_rights} vs inventory={inv_rights}")
            effective_rights = inv_rights or str(declared_rights or "UNKNOWN_RIGHTS").strip()

        if effective_rights in BLOCKED_RIGHTS or effective_rights not in ALLOWED_RIGHTS:
            errors.append(f"FORBIDDEN_RIGHTS_IN_FINAL_EDL: {label} ({src_id}) has rights={effective_rights}")
            return

        if validation_mode == "release":
            if effective_rights == "LICENSED":
                entry = ledger.get(src_id)
                if not entry:
                    errors.append(f"MISSING_LICENSE_LEDGER_ENTRY: {label} ({src_id}) requires LICENSE_LEDGER.csv approval")
                else:
                    _check_ledger_evidence(label, src_id, entry, is_generated=False)
            elif effective_rights == "GENERATED":
                entry = ledger.get(src_id)
                if not entry:
                    errors.append(
                        f"MISSING_GENERATED_PROVENANCE: {label} ({src_id}) requires generator/model/voice provenance in LICENSE_LEDGER.csv"
                    )
                else:
                    _check_ledger_evidence(label, src_id, entry, is_generated=True)

    for shot in edl.get("shots", []):
        if isinstance(shot, dict):
            _check_item(str(shot.get("shot_id", "<shot>")), shot.get("source_id"), shot.get("source_rights"))
    for ac in edl.get("audio_tracks", []):
        if isinstance(ac, dict):
            _check_item(str(ac.get("clip_id", "<audio>")), ac.get("source_id"), ac.get("source_rights"))
    for ov in edl.get("overlays", []):
        if isinstance(ov, dict) and ov.get("source_id"):
            _check_item(str(ov.get("overlay_id", "<overlay>")), ov.get("source_id"), ov.get("source_rights"))

    return errors


def validate_claim_evidence(
    edl: dict[str, Any],
    claims: list[dict[str, Any]] | None = None,
    inventory: dict[str, dict[str, Any]] | None = None,
    run_dir: str | Path | None = None,
    validation_mode: str = "release",
) -> list[str]:
    errors: list[str] = []
    inv = inventory or {}
    claim_list = claims if claims is not None else edl.get("claims", [])
    edl_mode = str(edl.get("mode") or "").lower()
    claim_map: dict[str, dict[str, Any]] = {}

    for c in claim_list:
        if not isinstance(c, dict):
            errors.append("INVALID_CLAIM_RECORD_TYPE")
            continue
        cid = str(c.get("claim_id") or "").strip()
        if not cid:
            errors.append("MISSING_CLAIM_ID")
            continue
        if cid in claim_map:
            errors.append(f"DUPLICATE_CLAIM_ID: {cid}")
        claim_map[cid] = c

        status = str(c.get("status") or "").strip()
        if status not in VALID_CLAIM_STATUSES:
            errors.append(f"UNKNOWN_CLAIM_STATUS: {cid} status={status!r}")
            continue

        if status == "UNKNOWN_REMOVE":
            errors.append(f"UNVERIFIED_CLAIM_PRESENT: {cid} marked UNKNOWN_REMOVE must be deleted before EDL lock")
            continue

        text = str(c.get("text") or "")
        if status == "PLAUSIBLE_NOT_ADVERTISABLE":
            if edl_mode in COMMERCIAL_MODES and STRONG_COMMERCIAL_CLAIM_RE.search(text):
                errors.append(f"PLAUSIBLE_CLAIM_NOT_ADVERTISABLE: {cid} contains strong commercial claim in {edl_mode}")
            continue

        # VERIFIED_WITH_EVIDENCE checks
        ev_ref = str(c.get("evidence_ref") or "").strip()
        if not ev_ref:
            errors.append(f"MISSING_CLAIM_EVIDENCE_REF: {cid} has VERIFIED_WITH_EVIDENCE without evidence_ref")
            continue

        if ev_ref.startswith(("http://", "https://")):
            checked_at = str(c.get("checked_at") or "").strip()
            archive = str(c.get("evidence_archive_path") or "").strip()
            if not checked_at or not archive:
                errors.append(
                    f"UNVERIFIED_EXTERNAL_CLAIM_URI: {cid} external URL requires checked_at and local evidence_archive_path"
                )
            elif not _is_safe_relative_label(archive):
                errors.append(f"UNSAFE_CLAIM_EVIDENCE_REF: {cid} archive={archive!r}")
            elif run_dir is not None:
                root = Path(run_dir).resolve()
                target = (root / archive).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    errors.append(f"UNSAFE_CLAIM_EVIDENCE_REF: {cid} escapes run_dir")
                else:
                    if not target.exists():
                        errors.append(f"CLAIM_EVIDENCE_FILE_NOT_FOUND: {cid} -> {archive}")
        else:
            file_part, _, frag = ev_ref.partition("#")
            if not _is_safe_relative_label(file_part):
                errors.append(f"UNSAFE_CLAIM_EVIDENCE_REF: {cid} -> {ev_ref!r}")
                continue
            if frag and frag in inv:
                if str(inv[frag].get("rights_tag", "")).strip() in BLOCKED_RIGHTS:
                    errors.append(f"CLAIM_CITES_ANALYSIS_ONLY_SOURCE: {cid} cites blocked source {frag}")
            elif frag and validation_mode == "release" and inv and re.match(r"^[A-Z]{1,4}\d{1,4}$", frag):
                errors.append(f"CLAIM_EVIDENCE_SOURCE_MISSING: {cid} cites source {frag} not in inventory")

            if run_dir is not None:
                root = Path(run_dir).resolve()
                target = (root / file_part).resolve()
                try:
                    target.relative_to(root)
                except ValueError:
                    errors.append(f"UNSAFE_CLAIM_EVIDENCE_REF: {cid} escapes run_dir")
                else:
                    if not target.exists():
                        errors.append(f"CLAIM_EVIDENCE_FILE_NOT_FOUND: {cid} -> {file_part}")

        cited_src = str(c.get("source_id") or "").strip()
        if cited_src and cited_src in inv:
            if str(inv[cited_src].get("rights_tag", "")).strip() in BLOCKED_RIGHTS:
                errors.append(f"CLAIM_CITES_ANALYSIS_ONLY_SOURCE: {cid} source_id={cited_src}")

    for shot in edl.get("shots", []):
        if not isinstance(shot, dict):
            continue
        for cid in shot.get("claim_evidence_ids", []):
            if cid not in claim_map:
                errors.append(f"DANGLING_CLAIM_REF: {shot.get('shot_id')} references missing claim {cid}")
            elif claim_map[cid].get("status") == "UNKNOWN_REMOVE":
                errors.append(f"SHOT_USES_REMOVED_CLAIM: {shot.get('shot_id')} -> {cid}")
            elif (
                validation_mode == "release"
                and edl_mode in COMMERCIAL_MODES
                and claim_map[cid].get("status") == "PLAUSIBLE_NOT_ADVERTISABLE"
            ):
                errors.append(f"PLAUSIBLE_CLAIM_NOT_ADVERTISABLE: {shot.get('shot_id')} cites {cid} in {edl_mode}")

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
    out_w = spec.get("width", 0)
    out_h = spec.get("height", 0)
    out_w_i = out_w if _is_strict_int(out_w) else 0
    out_h_i = out_h if _is_strict_int(out_h) else 0

    if str(caption_policy).upper() == "OFF":
        for ov in edl.get("overlays", []):
            if not isinstance(ov, dict):
                continue
            otype = str(ov.get("overlay_type", "")).lower()
            if otype in {"caption", "captions", "karaoke", "subtitle", "subtitles"}:
                errors.append(f"UNAUTHORIZED_CAPTION_OVERLAY: {ov.get('overlay_id')} while caption_policy=OFF")

    for shot in edl.get("shots", []):
        if not isinstance(shot, dict):
            continue
        sid = shot.get("shot_id", "<shot>")
        safe = shot.get("safe_region_normalized")
        if safe is not None:
            valid_safe = (
                isinstance(safe, list)
                and len(safe) == 4
                and all(_is_finite_number(v) for v in safe)
                and 0.0 <= float(safe[0]) < float(safe[2]) <= 1.0
                and 0.0 <= float(safe[1]) < float(safe[3]) <= 1.0
            )
            if not valid_safe:
                errors.append(f"INVALID_SAFE_REGION: {sid} -> {safe!r}")

        src = inv.get(str(shot.get("source_id", "")))
        if src and out_w_i > 0 and out_h_i > 0:
            try:
                sw = int(src.get("width", 0))
                sh = int(src.get("height", 0))
            except (TypeError, ValueError):
                sw, sh = 0, 0
            if sw > sh and out_h_i > out_w_i:
                fm = shot.get("framing_mode")
                if fm not in VALID_FRAMING_MODES or fm == "native":
                    errors.append(f"LANDSCAPE_IN_PORTRAIT_NEEDS_EXPLICIT_FRAMING: {sid} has framing_mode={fm}")

    return errors


def validate_all(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]] | None = None,
    license_ledger: dict[str, dict[str, Any]] | None = None,
    brief: dict[str, Any] | None = None,
    run_dir: str | Path | None = None,
    validation_mode: str = "release",
) -> dict[str, Any]:
    if validation_mode not in {"release", "draft"}:
        raise ValueError(f"Unsupported validation_mode: {validation_mode!r}")

    inv = inventory or {}
    checks = {
        "frame_grid": validate_frame_grid(edl),
        "source_ranges": validate_source_ranges(edl, inv, validation_mode=validation_mode),
        "timeline_coverage": validate_timeline_coverage(edl),
        "asset_rights": validate_asset_rights(edl, inv, license_ledger, run_dir=run_dir, validation_mode=validation_mode),
        "claim_evidence": validate_claim_evidence(edl, inventory=inv, run_dir=run_dir, validation_mode=validation_mode),
        "mode_constraints": validate_mode_constraints(edl, inv, brief),
    }
    all_errors = [err for errs in checks.values() for err in errs]
    if all_errors:
        status = "FAIL_EDL_INVALID"
    elif validation_mode == "release":
        status = "PASS_EDL_VALID_FOR_RELEASE"
    else:
        status = "PASS_EDL_DRAFT_ONLY"

    return {
        "validation_mode": validation_mode,
        "status": status,
        "release_ready_edl": status == "PASS_EDL_VALID_FOR_RELEASE",
        "claim_review_note": "STRUCTURAL_EVIDENCE_CHECK_ONLY_HUMAN_FACT_REVIEW_SEPARATE",
        "ownership_note": "SHA256_VERIFIES_FILE_INTEGRITY_NOT_LEGAL_COPYRIGHT_OWNERSHIP",
        "error_count": len(all_errors),
        "checks": checks,
        "errors": all_errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed EDL validator before Concat MCP execution.")
    parser.add_argument("--edl", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, help="SOURCE_INVENTORY.csv or JSON (required for release mode).")
    parser.add_argument("--license-ledger", type=Path, help="LICENSE_LEDGER.csv (required for LICENSED/GENERATED assets).")
    parser.add_argument("--run-dir", type=Path, help="Optional run directory for resolving relative evidence paths.")
    parser.add_argument("--validation-mode", choices=["release", "draft"], default="release")
    parser.add_argument("--out", type=Path, help="Optional validation JSON output.")
    args = parser.parse_args(argv)

    edl = json.loads(args.edl.read_text(encoding="utf-8"))
    inv = _load_inventory_map(args.inventory)
    ledger = _load_ledger_map(args.license_ledger)
    result = validate_all(edl, inv, ledger, run_dir=args.run_dir, validation_mode=args.validation_mode)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["error_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
