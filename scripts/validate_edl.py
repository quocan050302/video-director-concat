#!/usr/bin/env python3
"""Fail-closed EDL validator separating draft, structural, and release (with on-disk source integrity).

Validation modes:
- draft: Planning-only check without full inventory; blocks ANALYSIS_ONLY/UNKNOWN_RIGHTS/UNKNOWN_REMOVE.
  Returns PASS_EDL_DRAFT_ONLY (release_ready=False).
- structural: Full metadata, rights, claim anchor, and frame-grid validation without requiring on-disk
  source hash verification. Returns PASS_EDL_STRUCTURAL_ONLY (release_ready=False).
- release (default): Requires structural validation PLUS verified per-file on-disk source integrity
  (from verify_source_hashes.py matching every referenced source_id, relative_label, and expected/actual
  SHA-256 against inventory). On C2/C4 (or require_source_integrity=True), missing/invalid integrity
  is a hard FAIL_EDL_INVALID; on C1 without integrity report, caps at PASS_EDL_STRUCTURAL_ONLY with
  release_ready=False and CLI exit 1 so release automation never confuses structural with final release.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
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
ISO_DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
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
    if "\x00" in label or any(ord(ch) < 32 for ch in label):
        return False
    if label.startswith(("/", "\\")):
        return False
    if re.match(r"^[A-Za-z]:", label):
        return False
    parts = re.split(r"[/\\]+", label)
    if ".." in parts:
        return False
    if Path(label).is_absolute():
        return False
    return True


def load_inventory_checked(path: str | Path | None) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not path:
        return {}, []
    p = Path(path)
    if not p.exists():
        return {}, [f"INVENTORY_FILE_NOT_FOUND: {p}"]
    if p.suffix.lower() == ".json":
        rows = json.loads(p.read_text(encoding="utf-8"))
    else:
        with open(p, "r", newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

    mapping: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for idx, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            errors.append(f"INVALID_INVENTORY_ROW_TYPE: row {idx}")
            continue
        sid = str(r.get("source_id") or "").strip()
        if not sid:
            errors.append(f"MISSING_INVENTORY_SOURCE_ID: row {idx}")
            continue
        if sid in mapping:
            errors.append(f"DUPLICATE_INVENTORY_SOURCE_ID: {sid} appears multiple times")
            continue
        mapping[sid] = r
    return mapping, errors


def load_ledger_checked(path: str | Path | None) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not path:
        return {}, []
    p = Path(path)
    if not p.exists():
        return {}, []
    with open(p, "r", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    mapping: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for idx, r in enumerate(rows, start=1):
        key = str(r.get("asset_id") or r.get("source_id") or "").strip()
        if not key:
            continue
        if key in mapping:
            errors.append(f"DUPLICATE_LEDGER_ASSET_ID: {key} appears multiple times (row {idx})")
            continue
        mapping[key] = r
    return mapping, errors


def _load_inventory_map(path: str | Path | None) -> dict[str, dict[str, Any]]:
    mapping, errs = load_inventory_checked(path)
    if errs:
        raise ValueError("; ".join(errs))
    return mapping


def _load_ledger_map(path: str | Path | None) -> dict[str, dict[str, Any]]:
    mapping, errs = load_ledger_checked(path)
    if errs:
        raise ValueError("; ".join(errs))
    return mapping


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

    w, h = spec.get("width"), spec.get("height")
    if w is not None and (not _is_strict_int(w) or w <= 0):
        errors.append(f"INVALID_OUTPUT_WIDTH: {w!r}")
    if h is not None and (not _is_strict_int(h) or h <= 0):
        errors.append(f"INVALID_OUTPUT_HEIGHT: {h!r}")

    for shot in edl.get("shots", []):
        if not isinstance(shot, dict):
            errors.append("INVALID_SHOT_RECORD_TYPE")
            continue
        sid = shot.get("shot_id", "<missing>")
        oin, oout = shot.get("output_in_frame"), shot.get("output_out_frame")
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
        oin, oout = ac.get("output_in_frame"), ac.get("output_out_frame")
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
    strict_inv = validation_mode in {"release", "structural"}
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

        sin, sout, speed_raw = shot.get("source_in_s"), shot.get("source_out_s"), shot.get("speed", 1.0)
        if not _is_finite_number(sin) or not _is_finite_number(sout) or float(sin) < 0.0 or float(sout) <= float(sin):
            errors.append(f"INVALID_SOURCE_RANGE: {sid} ({sin!r}..{sout!r})")
            continue
        if not _is_finite_number(speed_raw) or float(speed_raw) <= 0.0 or float(speed_raw) > 8.0:
            errors.append(f"INVALID_SPEED: {sid} speed={speed_raw!r}")
            continue

        sin_f, sout_f, speed = float(sin), float(sout), float(speed_raw)

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
        elif strict_inv or inventory:
            errors.append(f"SOURCE_ID_NOT_IN_INVENTORY: {sid} references {src_id}")

        oin, oout = shot.get("output_in_frame"), shot.get("output_out_frame")
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
        sin, sout = ac.get("source_in_s"), ac.get("source_out_s")
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
        elif strict_inv or inventory:
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
        p_out, c_in = prev["output_out_frame"], cur["output_in_frame"]
        if c_in > p_out:
            errors.append(f"TIMELINE_GAP: frames {p_out}..{c_in} between {prev.get('shot_id')} and {cur.get('shot_id')}")
        elif c_in < p_out:
            t_intent = str(cur.get("transition_intent", "")).lower()
            if not any(k in t_intent for k in ("dissolve", "crossfade", "overlap")):
                errors.append(f"UNINTENDED_OVERLAP: {prev.get('shot_id')} and {cur.get('shot_id')} overlap without dissolve intent")

    total_v1_end = max(s["output_out_frame"] for s in v1_sorted)
    for s in shots:
        if s.get("track", "V1") == "V1":
            continue
        oin, oout = s.get("output_in_frame"), s.get("output_out_frame")
        if _is_strict_int(oin) and _is_strict_int(oout) and oout > total_v1_end:
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


def _has_separate_generated_licenses(entry: dict[str, Any]) -> bool:
    code_lic = str(entry.get("code_license") or "").strip()
    model_lic = str(entry.get("model_or_voice_license") or entry.get("weights_license") or "").strip()
    if code_lic and model_lic:
        return True
    lic_name = str(entry.get("license_name") or "").lower()
    return ("code" in lic_name) and any(k in lic_name for k in ("weight", "model", "voice"))


def validate_asset_rights(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]],
    license_ledger: dict[str, dict[str, Any]] | None = None,
    run_dir: str | Path | None = None,
    validation_mode: str = "release",
) -> list[str]:
    errors: list[str] = []
    ledger = license_ledger or {}
    strict_inv = validation_mode in {"release", "structural"}

    if strict_inv and not inventory:
        return ["MISSING_SOURCE_INVENTORY: structural/release validation requires an independently probed SOURCE_INVENTORY"]

    def _check_ledger_evidence(label: str, src_id: str, entry: dict[str, Any], is_generated: bool) -> None:
        if entry.get("decision") != "APPROVED" or entry.get("commercial_use_allowed") != "YES":
            errors.append(f"UNVERIFIED_LICENSE: {label} ({src_id}) ledger decision/commercial_use not APPROVED+YES")
            return
        lic_ev = str(entry.get("license_evidence_path") or "").strip()
        if not lic_ev:
            errors.append(f"MISSING_LICENSE_EVIDENCE: {label} ({src_id}) requires archived license_evidence_path (URL alone is insufficient)")
        else:
            if not _is_safe_relative_label(lic_ev):
                errors.append(f"UNSAFE_LICENSE_EVIDENCE_PATH: {label} ({src_id}) -> {lic_ev}")
            elif run_dir is not None:
                root = Path(run_dir).resolve()
                raw_target = root / lic_ev
                if raw_target.is_symlink():
                    errors.append(f"UNSAFE_LICENSE_EVIDENCE_PATH: {label} ({src_id}) symlink rejected")
                else:
                    target = raw_target.resolve()
                    try:
                        target.relative_to(root)
                    except ValueError:
                        errors.append(f"UNSAFE_LICENSE_EVIDENCE_PATH: {label} ({src_id}) escapes run_dir")
                    else:
                        if not target.exists() or not target.is_file() or target.stat().st_size == 0:
                            errors.append(f"LICENSE_EVIDENCE_FILE_NOT_FOUND: {label} ({src_id}) -> {lic_ev}")

        if is_generated and not _has_separate_generated_licenses(entry):
            errors.append(
                f"MISSING_GENERATED_PROVENANCE: {label} ({src_id}) requires separate code and weights/model/voice licenses"
            )

    def _check_item(label: str, src_id: Any, declared_rights: Any) -> None:
        if not isinstance(src_id, str) or not src_id.strip():
            errors.append(f"INVALID_SOURCE_ID: {label}")
            return

        if strict_inv:
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
            inv_rights = str((inventory.get(src_id) or {}).get("rights_tag") or "").strip()
            if inv_rights and declared_rights and str(declared_rights).strip() != inv_rights:
                errors.append(f"SOURCE_RIGHTS_MISMATCH: {label} ({src_id}) EDL={declared_rights} vs inventory={inv_rights}")
            effective_rights = inv_rights or str(declared_rights or "UNKNOWN_RIGHTS").strip()

        if effective_rights in BLOCKED_RIGHTS or effective_rights not in ALLOWED_RIGHTS:
            errors.append(f"FORBIDDEN_RIGHTS_IN_FINAL_EDL: {label} ({src_id}) has rights={effective_rights}")
            return

        if strict_inv:
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
    verified_evidence_bundle: dict[str, str] | None = None,
    validation_mode: str = "release",
) -> list[str]:
    errors: list[str] = []
    inv = inventory or {}
    bundle = verified_evidence_bundle or {}
    strict_mode = validation_mode in {"release", "structural"}
    claim_list = claims if claims is not None else edl.get("claims", [])
    edl_mode = str(edl.get("mode") or "").lower()
    claim_map: dict[str, dict[str, Any]] = {}

    def _resolve_and_check_content(cid: str, rel_file: str, anchor: str) -> None:
        if not _is_safe_relative_label(rel_file):
            errors.append(f"UNSAFE_CLAIM_EVIDENCE_REF: {cid} -> {rel_file!r}")
            return
        if rel_file in bundle:
            content = bundle[rel_file]
            if not content.strip():
                errors.append(f"CLAIM_EVIDENCE_FILE_EMPTY: {cid} -> {rel_file}")
            elif anchor and anchor not in content:
                errors.append(f"CLAIM_EVIDENCE_ANCHOR_NOT_FOUND: {cid} anchor={anchor!r} missing in {rel_file}")
            return
        if run_dir is None:
            if strict_mode:
                errors.append(f"MISSING_RUN_DIR_FOR_CLAIM_EVIDENCE: {cid} cannot verify {rel_file!r} without run_dir")
            return

        root = Path(run_dir).resolve()
        raw_target = root / rel_file
        if raw_target.is_symlink():
            errors.append(f"UNSAFE_CLAIM_EVIDENCE_REF: {cid} symlink rejected")
            return
        target = raw_target.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append(f"UNSAFE_CLAIM_EVIDENCE_REF: {cid} escapes run_dir")
            return
        if not target.exists() or not target.is_file():
            errors.append(f"CLAIM_EVIDENCE_FILE_NOT_FOUND: {cid} -> {rel_file}")
            return
        content = target.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            errors.append(f"CLAIM_EVIDENCE_FILE_EMPTY: {cid} -> {rel_file}")
        elif anchor and anchor not in content:
            errors.append(f"CLAIM_EVIDENCE_ANCHOR_NOT_FOUND: {cid} anchor={anchor!r} missing in {rel_file}")

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

        ev_ref = str(c.get("evidence_ref") or "").strip()
        if not ev_ref:
            errors.append(f"MISSING_CLAIM_EVIDENCE_REF: {cid} has VERIFIED_WITH_EVIDENCE without evidence_ref")
            continue

        if ev_ref.startswith(("http://", "https://")):
            checked_at = str(c.get("checked_at") or "").strip()
            archive = str(c.get("evidence_archive_path") or "").strip()
            if not checked_at or not ISO_DATE_PREFIX_RE.match(checked_at) or not archive:
                errors.append(
                    f"UNVERIFIED_EXTERNAL_CLAIM_URI: {cid} external URL requires ISO checked_at and local evidence_archive_path"
                )
            else:
                _resolve_and_check_content(cid, archive, "")
        else:
            file_part, _, frag = ev_ref.partition("#")
            if frag and frag in inv:
                if str(inv[frag].get("rights_tag", "")).strip() in BLOCKED_RIGHTS:
                    errors.append(f"CLAIM_CITES_ANALYSIS_ONLY_SOURCE: {cid} cites blocked source {frag}")
            elif frag and strict_mode and inv and re.match(r"^[A-Z]{1,4}\d{1,4}$", frag):
                errors.append(f"CLAIM_EVIDENCE_SOURCE_MISSING: {cid} cites source {frag} not in inventory")
            _resolve_and_check_content(cid, file_part, frag)

        cited_src = str(c.get("source_id") or "").strip()
        if cited_src:
            if strict_mode and cited_src not in inv:
                errors.append(f"CLAIM_SOURCE_ID_NOT_IN_INVENTORY: {cid} source_id={cited_src}")
            elif cited_src in inv and str(inv[cited_src].get("rights_tag", "")).strip() in BLOCKED_RIGHTS:
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
                strict_mode
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
    out_w_i = spec.get("width", 0) if _is_strict_int(spec.get("width")) else 0
    out_h_i = spec.get("height", 0) if _is_strict_int(spec.get("height")) else 0

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
                sw, sh = int(src.get("width", 0)), int(src.get("height", 0))
            except (TypeError, ValueError):
                sw, sh = 0, 0
            if sw > sh and out_h_i > out_w_i:
                fm = shot.get("framing_mode")
                if fm not in VALID_FRAMING_MODES or fm == "native":
                    errors.append(f"LANDSCAPE_IN_PORTRAIT_NEEDS_EXPLICIT_FRAMING: {sid} has framing_mode={fm}")

    return errors


def _evaluate_source_integrity(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]],
    source_integrity_report: dict[str, Any] | None,
    require_source_integrity: bool,
) -> tuple[str, bool, list[str]]:
    """Verify per-file on-disk SHA-256 report from verify_source_hashes.py against EDL & inventory."""
    if not source_integrity_report:
        if require_source_integrity:
            return (
                "FAIL_SOURCE_INTEGRITY_MISSING",
                False,
                ["MISSING_SOURCE_INTEGRITY_CHECK: release gate requires verify_source_hashes.py pre/post check"],
            )
        return "SOURCE_INTEGRITY_NOT_VERIFIED_ON_DISK", False, []

    errors: list[str] = []
    if not isinstance(source_integrity_report, dict):
        return "FAIL_SOURCE_INTEGRITY_INVALID", False, ["SOURCE_INTEGRITY_REPORT_INVALID_TYPE"]

    if _parse_iso_ts(source_integrity_report.get("checked_at")) is None:
        errors.append("SOURCE_INTEGRITY_MISSING_CHECKED_AT")

    if source_integrity_report.get("status") != "PASS_SOURCES_UNCHANGED":
        errors.append("SOURCE_INTEGRITY_DRIFT_OR_FAILURE")

    entries = source_integrity_report.get("entries")
    if not isinstance(entries, list) or not entries:
        errors.append("SOURCE_INTEGRITY_EMPTY_ENTRIES")
        return "FAIL_SOURCE_INTEGRITY_INVALID", False, errors

    verified_by_id: dict[str, dict[str, Any]] = {}
    for e in entries:
        if not isinstance(e, dict):
            errors.append("SOURCE_INTEGRITY_ENTRY_INVALID_TYPE")
            continue
        sid = str(e.get("source_id") or "").strip()
        if not sid:
            errors.append("SOURCE_INTEGRITY_ENTRY_MISSING_ID")
            continue
        if sid in verified_by_id:
            errors.append(f"SOURCE_INTEGRITY_DUPLICATE_ID: {sid}")
            continue
        verified_by_id[sid] = e

    needed_ids = set()
    for grp in (edl.get("shots", []), edl.get("audio_tracks", []), edl.get("overlays", [])):
        for item in grp:
            if isinstance(item, dict) and item.get("source_id"):
                needed_ids.add(str(item["source_id"]))

    for sid in sorted(needed_ids):
        e = verified_by_id.get(sid)
        if not e:
            errors.append(f"SOURCE_INTEGRITY_MISSING_ID: {sid}")
            continue
        if e.get("status") != "UNCHANGED":
            errors.append(f"SOURCE_INTEGRITY_NOT_UNCHANGED: {sid} status={e.get('status')!r}")
        exp_sha = str(e.get("expected_sha256") or "").strip().lower()
        act_sha = str(e.get("actual_sha256") or "").strip().lower()
        rel_lbl = str(e.get("relative_label") or "").strip()
        if not SHA256_RE.match(exp_sha) or not SHA256_RE.match(act_sha) or not rel_lbl:
            errors.append(f"SOURCE_INTEGRITY_ENTRY_INCOMPLETE: {sid} requires valid expected_sha256, actual_sha256, and relative_label")
            continue
        if exp_sha != act_sha:
            errors.append(f"SOURCE_INTEGRITY_SHA_MISMATCH: {sid} expected!=actual")
        inv_meta = inventory.get(sid)
        if inv_meta:
            inv_sha = str(inv_meta.get("sha256") or "").strip().lower()
            if inv_sha and act_sha != inv_sha:
                errors.append(f"SOURCE_INTEGRITY_SHA_MISMATCH: {sid} report SHA != inventory SHA")
            inv_rel = str(inv_meta.get("relative_label") or "").strip()
            if inv_rel and rel_lbl != inv_rel:
                errors.append(f"SOURCE_INTEGRITY_LABEL_MISMATCH: {sid} report={rel_lbl!r} inventory={inv_rel!r}")

    if errors:
        return "FAIL_SOURCE_INTEGRITY_INVALID", False, errors
    return "PASS_SOURCE_INTEGRITY", True, []


def validate_all(
    edl: dict[str, Any],
    inventory: dict[str, dict[str, Any]] | None = None,
    license_ledger: dict[str, dict[str, Any]] | None = None,
    brief: dict[str, Any] | None = None,
    run_dir: str | Path | None = None,
    verified_evidence_bundle: dict[str, str] | None = None,
    source_integrity_report: dict[str, Any] | None = None,
    require_source_integrity: bool = False,
    loader_errors: list[str] | None = None,
    validation_mode: str = "release",
    gate_phase: str = "C1",
) -> dict[str, Any]:
    if validation_mode not in {"release", "structural", "draft"}:
        raise ValueError(f"Unsupported validation_mode: {validation_mode!r}")
    if gate_phase not in {"C1", "C2", "C4"}:
        raise ValueError(f"Unsupported gate_phase: {gate_phase!r}")

    inv = inventory or {}
    # C2/C4 in release mode ALWAYS require verified on-disk source integrity (fail-closed!)
    effective_require_integrity = bool(
        require_source_integrity or (validation_mode == "release" and gate_phase in {"C2", "C4"})
    )
    int_status, int_pass, int_errors = _evaluate_source_integrity(
        edl, inv, source_integrity_report, require_source_integrity=effective_require_integrity
    )

    checks = {
        "loader_integrity": list(loader_errors or []),
        "frame_grid": validate_frame_grid(edl),
        "source_ranges": validate_source_ranges(edl, inv, validation_mode=validation_mode),
        "timeline_coverage": validate_timeline_coverage(edl),
        "asset_rights": validate_asset_rights(edl, inv, license_ledger, run_dir=run_dir, validation_mode=validation_mode),
        "claim_evidence": validate_claim_evidence(
            edl, inventory=inv, run_dir=run_dir,
            verified_evidence_bundle=verified_evidence_bundle, validation_mode=validation_mode,
        ),
        "mode_constraints": validate_mode_constraints(edl, inv, brief),
        "source_integrity": int_errors,
    }
    structural_errors = [
        err for k, errs in checks.items() if k != "source_integrity" for err in errs
    ]
    all_errors = [err for errs in checks.values() for err in errs]
    structural_pass = len(structural_errors) == 0

    if all_errors:
        status = "FAIL_EDL_INVALID"
        release_ready = False
    elif validation_mode == "draft":
        status = "PASS_EDL_DRAFT_ONLY"
        release_ready = False
    elif validation_mode == "structural":
        status = "PASS_EDL_STRUCTURAL_ONLY"
        release_ready = False
    else:
        # validation_mode == "release": NEVER emit PASS_EDL_VALID_FOR_RELEASE unless source_integrity_pass is True!
        if int_pass:
            status = "PASS_EDL_VALID_FOR_RELEASE"
            release_ready = True
        else:
            status = "PASS_EDL_STRUCTURAL_ONLY"
            release_ready = False

    return {
        "validation_mode": validation_mode,
        "gate_phase": gate_phase,
        "status": status,
        "structural_pass": structural_pass,
        "source_integrity_pass": int_pass,
        "release_ready": release_ready,
        "release_ready_edl": release_ready,
        "source_integrity_status": int_status,
        "claim_review_note": "STRUCTURAL_EVIDENCE_CHECK_ONLY_HUMAN_FACT_REVIEW_SEPARATE",
        "ownership_note": "OWNER_PROVENANCE_AND_SHA256_NOT_CRYPTOGRAPHIC_LEGAL_OWNERSHIP",
        "error_count": len(all_errors),
        "checks": checks,
        "errors": all_errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed EDL validator (draft / structural / release).")
    parser.add_argument("--edl", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, help="SOURCE_INVENTORY.csv or JSON (required for structural/release).")
    parser.add_argument("--license-ledger", type=Path, help="LICENSE_LEDGER.csv (required for LICENSED/GENERATED assets).")
    parser.add_argument("--run-dir", type=Path, help="Run directory for resolving claim/license evidence paths.")
    parser.add_argument("--source-integrity", type=Path, help="JSON report from verify_source_hashes.py (required for release).")
    parser.add_argument("--require-source-integrity", action="store_true", help="Explicitly fail if source integrity missing.")
    parser.add_argument("--validation-mode", choices=["release", "structural", "draft"], default="release")
    parser.add_argument("--gate-phase", choices=["C1", "C2", "C4"], default="C1")
    parser.add_argument("--out", type=Path, help="Optional validation JSON output.")
    args = parser.parse_args(argv)

    edl = json.loads(args.edl.read_text(encoding="utf-8"))
    inv, inv_errs = load_inventory_checked(args.inventory)
    ledger, led_errs = load_ledger_checked(args.license_ledger)
    src_int = json.loads(args.source_integrity.read_text(encoding="utf-8")) if args.source_integrity else None
    result = validate_all(
        edl, inv, ledger,
        run_dir=args.run_dir,
        source_integrity_report=src_int,
        require_source_integrity=args.require_source_integrity,
        loader_errors=inv_errs + led_errs,
        validation_mode=args.validation_mode,
        gate_phase=args.gate_phase,
    )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.validation_mode == "release":
        return 0 if result["release_ready"] else 1
    return 0 if result["error_count"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
