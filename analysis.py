"""Forensic image analysis functions for the CSAFE AI Image Alteration Tracker.

Each function is pure (no Flask dependency) and operates on a file path or
tag dict. Entry point for the full pipeline is _run_analysis_pipeline().
"""

import base64
import io
import json
import pathlib
import re
import subprocess

import numpy as np
from PIL import Image, ImageChops, ImageFilter

METADATA_DIR = pathlib.Path(__file__).parent / "metadata"
METADATA_DIR.mkdir(exist_ok=True)

# Fields produced by exiftool that are file-level or derived, not embedded metadata.
_SKIP_FIELDS = {
    "SourceFile", "ExifToolVersion", "FileName", "Directory", "FileSize",
    "FileModifyDate", "FileAccessDate", "FileInodeChangeDate", "FilePermissions",
    "FileType", "FileTypeExtension", "MIMEType", "ImageWidth", "ImageHeight",
    "EncodingProcess", "BitsPerSample", "ColorComponents", "YCbCrSubSampling",
    "Megapixels", "ImageSize",
}

# Tag key suffixes (after the "Group:" prefix) that should never be checked
# for AI software strings, because they contain file paths or other values
# that could cause false positives.
_SKIP_KEY_SUFFIXES = {
    "Directory", "FileName", "SourceFile", "FilePath", "FileModifyDate",
    "FileAccessDate", "FileInodeChangeDate", "FilePermissions",
}

_AI_SOFTWARE_STRINGS = [
    "adobe firefly", "dall-e", "dall·e", "midjourney", "stable diffusion",
    "imagen", "grok", "gemini", "chatgpt", "openai", "ideogram", "runway",
    "leonardo", "adobe generative", "generative fill",
]


def _run_exiftool(path: pathlib.Path) -> dict:
    """Run exiftool on path and return a flat tag dict. Returns {} if not installed."""
    try:
        result = subprocess.run(
            ["exiftool", "-json", "-a", "-G1", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        return data[0] if data else {}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def _analyze_exif(tags: dict) -> str:
    """Return a human-readable string of EXIF anomalies for an AI-altered image."""
    notes = []

    # Check for AI software strings in any tag value.
    for key, val in tags.items():
        if key in _SKIP_FIELDS:
            continue
        # Also skip by suffix (handles "Group:FieldName" style keys from exiftool -G1).
        suffix = key.split(":")[-1] if ":" in key else key
        if suffix in _SKIP_KEY_SUFFIXES:
            continue
        val_lower = str(val).lower()
        for ai_str in _AI_SOFTWARE_STRINGS:
            if ai_str in val_lower:
                notes.append(f"{key}: '{val}' (AI software tag)")
                break

    # Flag missing expected camera fields.
    has_make = any(k.endswith("Make") for k in tags)
    has_model = any(k.endswith("Model") for k in tags)
    has_datetime = any("DateTimeOriginal" in k for k in tags)
    if not has_make:
        notes.append("Camera Make absent")
    if not has_model:
        notes.append("Camera Model absent")
    if not has_datetime:
        notes.append("DateTimeOriginal absent")

    # Flag absent GPS.
    has_gps = any(k.startswith("GPS") or "GPS" in k for k in tags)
    if not has_gps:
        notes.append("GPS data absent")

    if not notes:
        return "No anomalies detected."
    return "\n".join(f"• {n}" for n in notes)


def _check_c2pa(path: pathlib.Path, tags: dict) -> str:
    """Check for C2PA / Content Credentials. Returns one of the three dropdown values.

    Detection order:
    1. c2patool CLI (most authoritative)
    2. JUMBF tags in the pre-extracted exiftool output (covers PNG/JPEG C2PA blocks)
    3. XMP namespace check via Pillow (last resort)
    """
    # 1. Try c2patool first.
    try:
        result = subprocess.run(
            ["c2patool", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout + result.stderr
        if result.returncode == 0 and output.strip():
            output_lower = output.lower()
            if "no claim" in output_lower or "no manifest" in output_lower:
                return "No"
            if "ingredient" in output_lower or "claim_generator" in output_lower or "assertions" in output_lower:
                return "Yes — with provenance data"
            return "Yes — but empty / stripped"
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        pass

    # 2. Check JUMBF tags from exiftool output.
    # exiftool exposes C2PA manifests embedded in PNG/JPEG as JUMBF:JUMDLabel = "c2pa".
    for key, val in tags.items():
        if "JUMBF" in key and "c2pa" in str(val).lower():
            return "Yes — with provenance data"

    # 3. Fallback: check XMP data via Pillow for c2pa namespace.
    try:
        with Image.open(path) as img:
            xmp = img.info.get("xmp", b"")
            if isinstance(xmp, bytes):
                xmp = xmp.decode("utf-8", errors="ignore")
            if "c2pa" in xmp.lower():
                return "Yes — with provenance data"
    except Exception:
        pass

    return "No"


def _extract_c2pa_details_from_c2patool(path: pathlib.Path) -> dict | None:
    """Parse c2patool JSON output into the same dict shape as _extract_c2pa_details."""
    try:
        result = subprocess.run(
            ["c2patool", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        data = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None

    active_key = data.get("active_manifest")
    manifests  = data.get("manifests", {})
    manifest   = manifests.get(active_key) or (next(iter(manifests.values()), None) if manifests else None)
    if not manifest:
        return None

    sig      = manifest.get("signature_info") or {}
    cg_info  = manifest.get("claim_generator_info") or []
    cg_name  = cg_info[0].get("name") if cg_info else manifest.get("claim_generator")

    raw_actions = []
    for assertion in manifest.get("assertions") or []:
        if assertion.get("label", "").startswith("c2pa.actions"):
            for a in (assertion.get("data") or {}).get("actions") or []:
                act = a.get("action", "")
                raw_actions.append(act.replace("c2pa.", ""))

    return {
        "claim_generator":     cg_name,
        "software_agent":      sig.get("issuer"),
        "c2pa_version":        None,
        "actions":             raw_actions or None,
        "digital_source_type": None,
        "validation_failures": None,
        "validation_failure_explanations": None,
        "manifest_id":         active_key,
    }


def _extract_c2pa_details(tags: dict, path: pathlib.Path | None = None) -> dict | None:
    """Extract human-readable C2PA provenance fields from exiftool tags.

    Falls back to c2patool JSON output when JUMBF tags are absent.
    Returns a dict with the most forensically relevant fields, or None if no
    C2PA data is present.
    """
    if not any("JUMBF" in k and "c2pa" in str(v).lower() for k, v in tags.items()):
        if path is not None:
            return _extract_c2pa_details_from_c2patool(path)
        return None

    def _get(key):
        return tags.get(f"CBOR:{key}")

    # Digital source type: extract last path segment from IPTC URI.
    dst_raw = _get("ActionsDigitalSourceType") or ""
    if isinstance(dst_raw, list):
        dst_raw = dst_raw[0] if dst_raw else ""
    digital_source_type = dst_raw.rstrip("/").rsplit("/", 1)[-1] if dst_raw else None

    # Actions: normalise to list and strip "c2pa." prefix for readability.
    actions_raw = _get("ActionsAction") or []
    if isinstance(actions_raw, str):
        actions_raw = [actions_raw]
    actions = [a.replace("c2pa.", "") for a in actions_raw]

    # Validation: collect failure codes/explanations.
    fail_codes = _get("ValidationResultsActiveManifestFailureCode") or []
    if isinstance(fail_codes, str):
        fail_codes = [fail_codes]
    fail_explanations = _get("ValidationResultsActiveManifestFailureExplanation") or []
    if isinstance(fail_explanations, str):
        fail_explanations = [fail_explanations]

    # Active manifest ID: first urn:c2pa:... label from JUMBF.
    manifest_id = None
    for val in tags.values():
        if isinstance(val, str) and val.startswith("urn:c2pa:"):
            manifest_id = val
            break

    return {
        "claim_generator":      _get("Claim_Generator_InfoName"),
        "software_agent":       _get("ActionsSoftwareAgentName"),
        "c2pa_version":         _get("Claim_Generator_InfoOrgContentauthC2Pa_Rs"),
        "actions":              actions or None,
        "digital_source_type":  digital_source_type or None,
        "validation_failures":  fail_codes or None,
        "validation_failure_explanations": fail_explanations or None,
        "manifest_id":          manifest_id,
    }


def _run_ela(path: pathlib.Path) -> tuple[bool, int, float, float, str, str]:
    """Run Error Level Analysis at quality 75 (standard ELA practice).

    Returns (flagged, max_diff, mean_diff, std_diff, ela_source, base64_png).
    ela_source is 'jpeg' or 'png'; PNG images are re-compressed as JPEG for
    the first time so their ELA values reflect first-time compression artifacts,
    not tampering.
    """
    ELA_QUALITY = 75
    ELA_SCALE = 10
    ELA_THRESHOLD = 15

    try:
        with Image.open(path) as img:
            ela_source = 'png' if (img.format or '').upper() == 'PNG' else 'jpeg'
            img_rgb = img.convert("RGB")

        buf = io.BytesIO()
        img_rgb.save(buf, format="JPEG", quality=ELA_QUALITY)
        buf.seek(0)
        recompressed = Image.open(buf).convert("RGB")

        diff = ImageChops.difference(img_rgb, recompressed)
        diff_arr = np.array(diff)
        max_diff  = int(diff_arr.max())
        mean_diff = float(diff_arr.mean())
        std_diff  = float(diff_arr.std())

        # Scale up for visibility.
        scaled = diff_arr * ELA_SCALE
        scaled = np.clip(scaled, 0, 255).astype("uint8")
        ela_img = Image.fromarray(scaled, "RGB")

        out_buf = io.BytesIO()
        ela_img.save(out_buf, format="PNG")
        b64 = base64.b64encode(out_buf.getvalue()).decode("ascii")

        return max_diff > ELA_THRESHOLD, max_diff, mean_diff, std_diff, ela_source, b64
    except Exception:
        return False, 0, 0.0, 0.0, 'unknown', ""


def _check_noise_inconsistency(path: pathlib.Path) -> tuple[bool, float, float, float, str]:
    """Estimate per-block noise and flag regions with inconsistent levels.

    Returns (flagged, noise_std, noise_skewness, noise_kurtosis, note).
    """
    BLOCK_SIZE = 64
    THRESHOLD = 1.5  # std of block noise estimates

    try:
        with Image.open(path) as img:
            gray = np.array(img.convert("L"), dtype=float)

        h, w = gray.shape
        # Simple high-pass: subtract 3×3 mean.
        with Image.open(path) as img:
            blurred = np.array(img.convert("L").filter(ImageFilter.BoxBlur(3)), dtype=float)
        hp = gray - blurred

        block_noises = []
        for y in range(0, h - BLOCK_SIZE + 1, BLOCK_SIZE):
            for x in range(0, w - BLOCK_SIZE + 1, BLOCK_SIZE):
                block = hp[y:y + BLOCK_SIZE, x:x + BLOCK_SIZE]
                block_noises.append(float(np.std(block)))

        if not block_noises:
            return False, 0.0, 0.0, 0.0, ""

        noise_arr  = np.array(block_noises)
        noise_std  = float(np.std(noise_arr))
        mean_bn    = float(np.mean(noise_arr))
        diffs      = noise_arr - mean_bn
        noise_skew = float(np.mean(diffs ** 3) / (noise_std ** 3 + 1e-9))
        noise_kurt = float(np.mean(diffs ** 4) / (noise_std ** 4 + 1e-9)) - 3.0
        flagged    = noise_std > THRESHOLD
        note = f"Noise inconsistency: block noise std={noise_std:.2f} (threshold {THRESHOLD})."
        return flagged, noise_std, noise_skew, noise_kurt, note if flagged else ""
    except Exception:
        return False, 0.0, 0.0, 0.0, ""


def _check_compression_blocking(path: pathlib.Path) -> tuple[bool, str]:
    """Detect DCT blocking artifacts in JPEG images."""
    BLOCK_SIZE = 8
    RATIO_THRESHOLD = 1.3

    try:
        with Image.open(path) as img:
            if (img.format or "").upper() not in ("JPEG", "JPG"):
                return False, ""
            gray = np.array(img.convert("L"), dtype=float)

        h, w = gray.shape

        # Mean absolute difference at 8-pixel boundaries vs. one pixel away.
        boundary_diffs, interior_diffs = [], []
        for y in range(BLOCK_SIZE, h - 1, BLOCK_SIZE):
            row_diff = np.mean(np.abs(gray[y, :] - gray[y - 1, :]))
            inner_diff = np.mean(np.abs(gray[y - 1, :] - gray[y - 2, :]))
            boundary_diffs.append(row_diff)
            interior_diffs.append(inner_diff)
        for x in range(BLOCK_SIZE, w - 1, BLOCK_SIZE):
            col_diff = np.mean(np.abs(gray[:, x] - gray[:, x - 1]))
            inner_diff = np.mean(np.abs(gray[:, x - 1] - gray[:, x - 2]))
            boundary_diffs.append(col_diff)
            interior_diffs.append(inner_diff)

        if not boundary_diffs or not interior_diffs:
            return False, ""

        avg_boundary = float(np.mean(boundary_diffs))
        avg_interior = float(np.mean(interior_diffs))
        if avg_interior == 0:
            return False, ""

        ratio = avg_boundary / avg_interior
        flagged = ratio > RATIO_THRESHOLD
        note = f"Compression blocking: boundary/interior diff ratio={ratio:.2f} (threshold {RATIO_THRESHOLD})."
        return flagged, note if flagged else ""
    except Exception:
        return False, ""


def _detect_c2pa_from_tags(tags: dict) -> dict | None:
    """Extract C2PA data from exiftool CBOR/JUMBF tags."""
    has_jumbf = tags.get('JUMBF:JUMDLabel') == 'c2pa'
    has_cbor  = any(k.startswith('CBOR:') for k in tags)
    if not has_jumbf and not has_cbor:
        return None

    result: dict = {'status': 'found'}

    claim_gen = tags.get('CBOR:Claim_Generator_InfoName')
    if claim_gen:
        result['claim_generator'] = str(claim_gen)

    agent = tags.get('CBOR:ActionsSoftwareAgent') or tags.get('CBOR:ActionsSoftwareAgentName')
    if agent:
        result['software_agent'] = str(agent)

    c2pa_ver = tags.get('CBOR:Claim_Generator_InfoOrgContentauthC2Pa_Rs')
    if c2pa_ver:
        result['c2pa_version'] = str(c2pa_ver)

    raw_actions = tags.get('CBOR:ActionsAction')
    if raw_actions is not None:
        result['actions'] = [str(a) for a in (raw_actions if isinstance(raw_actions, list) else [raw_actions])]

    raw_dst = tags.get('CBOR:ActionsDigitalSourceType')
    if raw_dst is not None:
        dst = raw_dst[0] if isinstance(raw_dst, list) else raw_dst
        result['digital_source_type'] = str(dst).rstrip('/').split('/')[-1]

    instance_id = tags.get('CBOR:InstanceID')
    if instance_id:
        result['manifest_id'] = str(instance_id)

    raw_failures = tags.get('CBOR:ValidationResultsActiveManifestFailureCode')
    if raw_failures is not None:
        result['validation_failures'] = [str(f) for f in (raw_failures if isinstance(raw_failures, list) else [raw_failures])]
        raw_expl = tags.get('CBOR:ValidationResultsActiveManifestFailureExplanation')
        if raw_expl is not None:
            result['validation_failure_explanations'] = [str(e) for e in (raw_expl if isinstance(raw_expl, list) else [raw_expl])]

    return result


def _detect_indicators(tags: dict) -> dict:
    """Detect forensic indicators of AI generation from exiftool tags."""
    _CAMERA_KEYS = {
        'Make':             'IFD0:Make',
        'Model':            'IFD0:Model',
        'Software':         'IFD0:Software',
        'DateTimeOriginal': 'ExifIFD:DateTimeOriginal',
        'CreateDate':       'ExifIFD:CreateDate',
        'ISO':              'ExifIFD:ISO',
        'FocalLength':      'ExifIFD:FocalLength',
        'ExposureTime':     'ExifIFD:ExposureTime',
        'FNumber':          'ExifIFD:FNumber',
        'MeteringMode':     'ExifIFD:MeteringMode',
        'WhiteBalance':     'ExifIFD:WhiteBalance',
        'Flash':            'ExifIFD:Flash',
        'SceneType':        'ExifIFD:SceneType',
        'LensMake':         'ExifIFD:LensMake',
        'LensModel':        'ExifIFD:LensModel',
    }
    camera_present = {label: str(tags[key]) for label, key in _CAMERA_KEYS.items() if key in tags}
    camera_absent  = [label for label, key in _CAMERA_KEYS.items() if key not in tags]

    photoshop_adobe = {k: str(v) for k, v in tags.items() if k.startswith(('Photoshop:', 'Adobe:'))}

    icc_meas_view = {k: str(v) for k, v in tags.items() if k.startswith(('ICC-meas:', 'ICC-view:'))}

    artist       = str(tags.get('IFD0:Artist', ''))
    user_comment = str(tags.get('ExifIFD:UserComment', ''))
    grok_artist    = artist      if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-', artist.lower())      else None
    grok_signature = user_comment if user_comment.startswith('Signature:') else None
    grok_signatures = {'artist': grok_artist, 'user_comment': grok_signature} if (grok_artist or grok_signature) else None

    c2pa = _detect_c2pa_from_tags(tags)

    parts = []
    if camera_present:
        parts.append(f"Camera EXIF: present ({len(camera_present)} fields)")
    else:
        parts.append("Camera EXIF: absent")
    if photoshop_adobe:
        parts.append("Photoshop/Adobe markers detected")
    if icc_meas_view:
        parts.append("ICC measurement/viewing conditions detected")
    if grok_signatures:
        parts.append("Grok signature detected")
    if c2pa:
        parts.append("C2PA manifest detected")

    return {
        'summary':        ' | '.join(parts),
        'camera_exif':    {'present': camera_present, 'absent': camera_absent},
        'photoshop_adobe': photoshop_adobe or None,
        'icc_meas_view':  icc_meas_view or None,
        'grok_signatures': grok_signatures,
        'c2pa':           c2pa,
    }


def _run_analysis_pipeline(path: pathlib.Path) -> dict:
    """Run the full forensic analysis pipeline on an image file.

    Executes exiftool, ELA, noise inconsistency, compression blocking, and C2PA
    checks, then returns all results in a single dict ready to be stored in the record.
    """
    tags = _run_exiftool(path)
    if tags:
        meta_path = METADATA_DIR / (path.stem + ".json")
        meta_path.write_text(json.dumps(tags, indent=2))
    ifd0_tags      = {k: v for k, v in tags.items() if k.startswith("IFD0:")}
    indicators     = _detect_indicators(tags) if tags else None
    exif_anomalies = _analyze_exif(tags) if tags else "(exiftool not available)"
    c2pa_status    = _check_c2pa(path, tags)
    c2pa_details   = _extract_c2pa_details(tags, path)
    if indicators is not None and c2pa_status:
        c2pa_ind = {'status': c2pa_status}
        if c2pa_details:
            c2pa_ind.update({k: v for k, v in c2pa_details.items() if v is not None})
        already_detected = indicators.get('c2pa') is not None
        indicators['c2pa'] = c2pa_ind
        if not already_detected:
            indicators['summary'] += f' | C2PA: {c2pa_status}'
    ela_flagged, ela_max_diff, ela_mean_diff, ela_std_diff, ela_source, ela_b64 = _run_ela(path)
    noise_flagged, noise_std, noise_skewness, noise_kurtosis, noise_note = _check_noise_inconsistency(path)
    blocking_flagged, blocking_note = _check_compression_blocking(path)
    artifacts, notes = [], []
    if ela_flagged:
        artifacts.append("ELA anomaly")
        notes.append(f"ELA: max pixel diff={ela_max_diff} (threshold 15, quality 75).")
    if noise_flagged:
        artifacts.append("Noise inconsistency")
        notes.append(noise_note)
    if blocking_flagged:
        artifacts.append("Compression blocking")
        notes.append(blocking_note)
    return {
        "exif_anomalies":   exif_anomalies,
        "ifd0_tags":        ifd0_tags,
        "indicators":       indicators,
        "c2pa_status":      c2pa_status,
        "c2pa_details":     c2pa_details,
        "artifacts":        artifacts,
        "artifact_notes":   "\n".join(notes),
        "ela_image_b64":    ela_b64,
        "ela_max_diff":     ela_max_diff,
        "ela_mean_diff":    round(ela_mean_diff, 4),
        "ela_std_diff":     round(ela_std_diff, 4),
        "ela_source":       ela_source,
        "block_noise_std":  round(noise_std, 4),
        "noise_skewness":   round(noise_skewness, 4),
        "noise_kurtosis":   round(noise_kurtosis, 4),
    }
