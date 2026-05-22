"""
CSAFE AI Image Alteration Tracker — local Flask server.

Usage:
    pip install -r requirements.txt
    python app.py

Then open http://localhost:5000 in your browser.

Records are stored in a shared Supabase database. Copy .env.example to .env
and fill in your SUPABASE_URL and SUPABASE_KEY. Falls back to a local
records.json file if those variables are not set (useful for offline dev).

Images are searched recursively in 'real images/' and 'altered images/'.
"""

import base64
import io
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageFilter
from werkzeug.utils import secure_filename

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from flask import Flask, abort, jsonify, request, send_file

load_dotenv()

BASE = pathlib.Path(__file__).parent
DATA_FILE = BASE / "records.json"

_supabase = None
_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
if _SUPABASE_URL and _SUPABASE_KEY:
    from supabase import create_client
    _supabase = create_client(_SUPABASE_URL, _SUPABASE_KEY)

# All directories that may contain images.
IMAGE_ROOTS = [
    BASE / "real images",
    BASE / "altered images",
    BASE / "analyzed images",
]

UPLOAD_DIR    = BASE / "analyzed images"
METADATA_DIR  = BASE / "metadata"
METADATA_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(BASE / "static"))

@app.errorhandler(404)
def not_found(e):    return jsonify(error=str(e)), 404
@app.errorhandler(500)
def server_error(e): return jsonify(error="Internal server error"), 500


# ── Image search ──────────────────────────────────────────────────────────────

def find_image(filename: str) -> pathlib.Path | None:
    """Return the first file matching `filename` found under any IMAGE_ROOT.

    Also tries swapping .jpg <-> .jpeg so records and files on disk don't
    have to agree on the extension.
    """
    stem, _, ext = filename.rpartition(".")
    alt_ext = {"jpg": "jpeg", "jpeg": "jpg"}.get(ext.lower())
    candidates = [filename] + ([f"{stem}.{alt_ext}"] if alt_ext else [])

    for name in candidates:
        for root in IMAGE_ROOTS:
            if root.exists():
                for path in root.rglob(name):
                    if path.is_file():
                        return path
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    html = BASE / "tracker.html"
    if not html.exists():
        abort(404, "tracker.html not found next to app.py")
    return html.read_text(encoding="utf-8")


@app.route("/api/records", methods=["GET"])
def get_records():
    if _supabase:
        try:
            result = _supabase.table("records").select("data").execute()
            records = [row["data"] for row in result.data]
            for r in records:
                r.pop("ela_image_b64", None)
            return jsonify(records)
        except Exception as e:
            return jsonify({"error": str(e)}), 503
    if DATA_FILE.exists():
        return jsonify(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    return jsonify([])


@app.route("/api/records", methods=["POST"])
def set_records():
    data = request.get_json(force=True)
    if not isinstance(data, list):
        return jsonify({"error": "expected a JSON array"}), 400
    if _supabase:
        try:
            if data:
                ids = [r["id"] for r in data if "id" in r]
                rows = [{"id": r["id"], "data": r} for r in data if "id" in r]
                if rows:
                    _supabase.table("records").upsert(rows).execute()
                _supabase.table("records").delete().not_.in_("id", ids).execute()
            else:
                _supabase.table("records").delete().neq("id", "").execute()
        except Exception as e:
            return jsonify({"error": str(e)}), 503
        return jsonify({"ok": True, "count": len(data)})
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True, "count": len(data)})


@app.route("/api/records/<record_id>", methods=["POST"])
def set_record(record_id: str):
    rec = request.get_json(force=True)
    if not isinstance(rec, dict):
        return jsonify({"error": "expected a JSON object"}), 400
    if _supabase:
        try:
            storable = {k: v for k, v in rec.items() if k != "ela_image_b64"}
            _supabase.table("records").upsert({"id": record_id, "data": storable}).execute()
        except Exception as e:
            return jsonify({"error": str(e)}), 503
        return jsonify({"ok": True, "id": record_id})
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        data = [r for r in data if r.get("id") != record_id]
    else:
        data = []
    data.append(rec)
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True, "id": record_id})


@app.route("/api/records/<record_id>", methods=["DELETE"])
def delete_record(record_id: str):
    if _supabase:
        _supabase.table("records").delete().eq("id", record_id).execute()
    else:
        if DATA_FILE.exists():
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            data = [r for r in data if r.get("id") != record_id]
            DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True, "id": record_id})


@app.route("/images/<path:filename>")
def serve_image(filename: str):
    path = find_image(filename)
    if path is None:
        abort(404)
    return send_file(path)


# ── Model / file discovery ────────────────────────────────────────────────────

def find_model_folder(model: str) -> pathlib.Path | None:
    """Return the subfolder of 'altered images/' whose name matches model (case-insensitive)."""
    altered_root = BASE / "altered images"
    if not altered_root.exists():
        return None
    model_lower = model.lower()
    for d in altered_root.iterdir():
        if d.is_dir() and d.name.lower() == model_lower:
            return d
    return None


@app.route("/api/models")
def get_models():
    altered_root = BASE / "altered images"
    if not altered_root.exists():
        return jsonify([])
    models = sorted(
        d.name for d in altered_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    return jsonify(models)


def _format_filesize(size_bytes: int) -> str:
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} B"


@app.route("/api/original_image_info")
def original_image_info():
    filename = request.args.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "Missing filename"}), 400
    path = find_image(filename)
    if not path:
        return jsonify({"error": "File not found"}), 404
    try:
        size_str = _format_filesize(path.stat().st_size)
        with Image.open(path) as img:
            w, h = img.size
        return jsonify({"filesize": size_str, "dimensions": f"{w} \u00d7 {h}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/image_info")
def image_info():
    model = request.args.get("model", "").strip()
    filename = request.args.get("filename", "").strip()
    if not model or not filename:
        return jsonify({"error": "Missing parameters"}), 400
    model_dir = find_model_folder(model)
    if not model_dir:
        return jsonify({"error": "Model folder not found"}), 404
    path = model_dir / "downloaded" / filename
    if not path.is_file():
        return jsonify({"error": "File not found"}), 404
    try:
        with Image.open(path) as img:
            w, h = img.size
            fmt_map = {"JPEG": "JPEG", "PNG": "PNG", "WEBP": "WebP"}
            fmt = fmt_map.get((img.format or "").upper(), img.format or "")
            return jsonify({"format": fmt, "dimensions": f"{w} \u00d7 {h}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/original_files")
def get_original_files():
    if not ORIG_SRC_DIR.is_dir():
        return jsonify([])
    files = sorted(
        f.name for f in ORIG_SRC_DIR.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )
    return jsonify(files)


@app.route("/api/input_images")
def get_input_images():
    """Return original-renamed and modified images grouped by type."""
    orig_dir = BASE / "real images" / "02-original-renamed"
    mod_dir  = BASE / "real images" / "03-modified"

    def list_files(d):
        if not d.is_dir():
            return []
        return sorted(f.name for f in d.iterdir() if f.is_file() and not f.name.startswith("."))

    return jsonify({"original": list_files(orig_dir), "modified": list_files(mod_dir)})


@app.route("/api/downloaded_files")
def get_downloaded_files():
    model = request.args.get("model", "").strip()
    if not model:
        return jsonify({"error": "Missing model parameter"}), 400
    model_dir = find_model_folder(model)
    if not model_dir:
        return jsonify([])
    downloaded = model_dir / "downloaded"
    if not downloaded.is_dir():
        return jsonify([])
    files = sorted(
        f.name for f in downloaded.iterdir()
        if f.is_file() and not f.name.startswith(".")
    )
    return jsonify(files)


# ── Rename helpers ────────────────────────────────────────────────────────────

def _compute_renamed(input_image: str, ai_filename: str, model: str) -> tuple[str, bool]:
    """Return (dest_filename, already_exists).

    dest_filename follows the pattern  <input_stem>-b<NNN>.<ai_ext>  where NNN
    is the next unused three-digit sequence number, searched globally across
    all  altered images/*/renamed/  folders.
    """
    stem = input_image.rsplit(".", 1)[0] if "." in input_image else input_image
    ai_ext = ("." + ai_filename.rsplit(".", 1)[1]) if "." in ai_filename else ""

    # Find the highest existing sequence number for this stem (any extension).
    pattern = re.compile(
        r"^" + re.escape(stem) + r"-b(\d+)\.[^.]+$", re.IGNORECASE
    )
    max_num = 0
    altered_root = BASE / "altered images"
    if altered_root.exists():
        for renamed_dir in altered_root.glob("*/renamed"):
            if renamed_dir.is_dir():
                for f in renamed_dir.iterdir():
                    if f.is_file():
                        m = pattern.match(f.name)
                        if m:
                            max_num = max(max_num, int(m.group(1)))

    next_num = max_num + 1
    dest_filename = f"{stem}-b{next_num:03d}{ai_ext}"

    model_dir = find_model_folder(model)
    dest_path = (model_dir / "renamed" / dest_filename) if model_dir else None
    return dest_filename, bool(dest_path and dest_path.exists())


@app.route("/api/compute_renamed")
def compute_renamed_route():
    input_image = request.args.get("input_image", "").strip()
    ai_filename = request.args.get("ai_filename", "").strip()
    model = request.args.get("model", "").strip()
    if not (input_image and ai_filename and model):
        return jsonify({"error": "Missing required parameters"}), 400
    filename, already_exists = _compute_renamed(input_image, ai_filename, model)
    return jsonify({"filename": filename, "already_exists": already_exists})


@app.route("/api/copy_rename_image", methods=["POST"])
def copy_rename_image():
    data = request.get_json(force=True)
    input_image = (data.get("input_image") or "").strip()
    ai_filename = (data.get("ai_filename") or "").strip()
    model = (data.get("model") or "").strip()
    if not (input_image and ai_filename and model):
        return jsonify({"error": "Missing required parameters"}), 400

    dest_filename, already_exists = _compute_renamed(input_image, ai_filename, model)

    if already_exists:
        return jsonify({
            "ok": False,
            "warning": f"File already exists: {dest_filename}",
            "filename": dest_filename,
        })

    model_dir = find_model_folder(model)
    if not model_dir:
        return jsonify({"error": f"Model folder not found for: {model}"}), 404

    src_path = model_dir / "downloaded" / ai_filename
    if not src_path.is_file():
        return jsonify({
            "error": f"Source file not found: {model_dir.name}/downloaded/{ai_filename}"
        }), 404

    dest_dir = model_dir / "renamed"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest_dir / dest_filename)

    return jsonify({"ok": True, "filename": dest_filename})


# ── Original image rename helpers ────────────────────────────────────────────

ORIG_SRC_DIR  = BASE / "real images" / "01-original"
ORIG_DEST_DIR = BASE / "real images" / "02-original-renamed"


def _compute_original_renamed(original_filename: str, study_id: str) -> tuple[str, bool]:
    """Return (dest_filename, already_exists) for an original image rename.

    dest_filename is  <study_id>.<original_ext>  (e.g. csafe-001.jpg).
    already_exists is True if that file is already present in 02-original-renamed/.
    """
    ext = ("." + original_filename.rsplit(".", 1)[1]) if "." in original_filename else ""
    dest_filename = f"{study_id}{ext}"
    dest_path = ORIG_DEST_DIR / dest_filename
    return dest_filename, dest_path.exists()


@app.route("/api/compute_original_renamed")
def compute_original_renamed_route():
    original_filename = request.args.get("original_filename", "").strip()
    study_id = request.args.get("study_id", "").strip()
    if not (original_filename and study_id):
        return jsonify({"error": "Missing required parameters"}), 400
    filename, already_exists = _compute_original_renamed(original_filename, study_id)
    return jsonify({"filename": filename, "already_exists": already_exists})


@app.route("/api/copy_rename_original", methods=["POST"])
def copy_rename_original():
    data = request.get_json(force=True)
    original_filename = (data.get("original_filename") or "").strip()
    study_id = (data.get("study_id") or "").strip()
    if not (original_filename and study_id):
        return jsonify({"error": "Missing required parameters"}), 400

    dest_filename, already_exists = _compute_original_renamed(original_filename, study_id)

    if already_exists:
        return jsonify({
            "ok": False,
            "warning": f"File already exists: {dest_filename}",
            "filename": dest_filename,
        })

    src_path = ORIG_SRC_DIR / original_filename
    if not src_path.is_file():
        return jsonify({
            "error": f"Source file not found: 01-original/{original_filename}"
        }), 404

    ORIG_DEST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, ORIG_DEST_DIR / dest_filename)

    return jsonify({"ok": True, "filename": dest_filename})


MOD_DIR = BASE / "real images" / "03-modified"


@app.route("/api/upload_original", methods=["POST"])
def upload_original():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files['file']
    filename = secure_filename(f.filename)
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400
    ORIG_SRC_DIR.mkdir(parents=True, exist_ok=True)
    dest = ORIG_SRC_DIR / filename
    f.save(str(dest))
    return jsonify({"ok": True, "filename": filename})


@app.route("/api/upload_modified", methods=["POST"])
def upload_modified():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files['file']
    f_filename = secure_filename(f.filename)
    dest_filename = (request.form.get("dest_filename") or f_filename).strip()
    if not dest_filename:
        return jsonify({"error": "Invalid filename"}), 400
    MOD_DIR.mkdir(parents=True, exist_ok=True)
    dest = MOD_DIR / dest_filename
    if dest.exists():
        return jsonify({"ok": False, "warning": f"File already exists: {dest_filename}", "filename": dest_filename})
    f.save(str(dest))
    return jsonify({"ok": True, "filename": dest_filename})


@app.route("/api/upload_downloaded", methods=["POST"])
def upload_downloaded():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files['file']
    filename = secure_filename(f.filename)
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400
    model = (request.form.get("model") or "").strip()
    if not model:
        return jsonify({"error": "No model specified"}), 400
    model_dir = find_model_folder(model) or (BASE / "altered images" / model)
    downloaded = model_dir / "downloaded"
    downloaded.mkdir(parents=True, exist_ok=True)
    dest = downloaded / filename
    f.save(str(dest))
    return jsonify({"ok": True, "filename": filename})


@app.route("/api/rename_modified", methods=["POST"])
def rename_modified():
    data = request.get_json(force=True)
    current_filename = (data.get("current_filename") or "").strip()
    new_filename = (data.get("new_filename") or "").strip()
    if not (current_filename and new_filename):
        return jsonify({"error": "Missing required parameters"}), 400

    src_path = MOD_DIR / current_filename
    if not src_path.is_file():
        return jsonify({"error": f"File not found in 03-modified/: {current_filename}"}), 404

    dest_path = MOD_DIR / new_filename
    if dest_path.exists():
        return jsonify({"ok": False, "warning": f"File already exists: {new_filename}", "filename": new_filename})

    src_path.rename(dest_path)
    return jsonify({"ok": True, "filename": new_filename})


# ── Forensic analysis helpers ─────────────────────────────────────────────────

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


def _run_ela(path: pathlib.Path) -> tuple[bool, int, str]:
    """Run Error Level Analysis. Returns (flagged, max_diff, base64_png)."""
    ELA_QUALITY = 90
    ELA_SCALE = 10
    ELA_THRESHOLD = 15

    try:
        with Image.open(path) as img:
            img_rgb = img.convert("RGB")

        buf = io.BytesIO()
        img_rgb.save(buf, format="JPEG", quality=ELA_QUALITY)
        buf.seek(0)
        recompressed = Image.open(buf).convert("RGB")

        diff = ImageChops.difference(img_rgb, recompressed)
        diff_arr = np.array(diff)
        max_diff = int(diff_arr.max())

        # Scale up for visibility.
        scaled = diff_arr * ELA_SCALE
        scaled = np.clip(scaled, 0, 255).astype("uint8")
        ela_img = Image.fromarray(scaled, "RGB")

        out_buf = io.BytesIO()
        ela_img.save(out_buf, format="PNG")
        b64 = base64.b64encode(out_buf.getvalue()).decode("ascii")

        return max_diff > ELA_THRESHOLD, max_diff, b64
    except Exception:
        return False, 0, ""


def _check_noise_inconsistency(path: pathlib.Path) -> tuple[bool, str]:
    """Estimate per-block noise and flag regions with inconsistent levels."""
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
            return False, 0.0, ""

        noise_std = float(np.std(block_noises))
        flagged = noise_std > THRESHOLD
        note = f"Noise inconsistency: block noise std={noise_std:.2f} (threshold {THRESHOLD})."
        return flagged, noise_std, note if flagged else ""
    except Exception:
        return False, 0.0, ""


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

    artist      = str(tags.get('IFD0:Artist', ''))
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
    ela_flagged, ela_max_diff, ela_b64    = _run_ela(path)
    noise_flagged, noise_std, noise_note  = _check_noise_inconsistency(path)
    blocking_flagged, blocking_note       = _check_compression_blocking(path)
    artifacts, notes = [], []
    if ela_flagged:
        artifacts.append("ELA anomaly")
        notes.append(f"ELA: max pixel diff={ela_max_diff} (threshold 15).")
    if noise_flagged:
        artifacts.append("Noise inconsistency")
        notes.append(noise_note)
    if blocking_flagged:
        artifacts.append("Compression blocking")
        notes.append(blocking_note)
    return {
        "exif_anomalies":  exif_anomalies,
        "ifd0_tags":       ifd0_tags,
        "indicators":      indicators,
        "c2pa_status":     c2pa_status,
        "c2pa_details":    c2pa_details,
        "artifacts":       artifacts,
        "artifact_notes":  "\n".join(notes),
        "ela_image_b64":   ela_b64,
        "ela_max_diff":    ela_max_diff,
        "block_noise_std": round(noise_std, 4),
    }


@app.route("/api/analyze", methods=["POST"])
def analyze_image():
    data = request.get_json(force=True)
    altered_filename = (data.get("altered_filename") or "").strip()
    model = (data.get("model") or "").strip()

    if not (altered_filename and model):
        return jsonify({"error": "Missing required parameters"}), 400

    model_dir = find_model_folder(model)
    if not model_dir:
        return jsonify({"error": f"Model folder not found: {model}"}), 404
    altered_path = model_dir / "renamed" / altered_filename
    if not altered_path.is_file():
        return jsonify({"error": f"Altered image not found: {altered_filename}"}), 404

    try:
        return jsonify(_run_analysis_pipeline(altered_path))
    except Exception as e:
        logger.exception("analyze_image failed for %s", altered_filename)
        return jsonify({"error": f"Analysis failed: {e}"}), 500


@app.route("/api/analyze_file", methods=["POST"])
def analyze_file():
    """Analyze an already-uploaded file located anywhere in IMAGE_ROOTS."""
    data = request.get_json(force=True)
    filename = (data.get("filename") or "").strip()

    if not filename:
        return jsonify({"error": "Missing filename"}), 400

    path = find_image(filename)
    if not path:
        return jsonify({"error": f"File not found: {filename}"}), 404

    try:
        return jsonify(_run_analysis_pipeline(path))
    except Exception as e:
        logger.exception("analyze_file failed for %s", filename)
        return jsonify({"error": f"Analysis failed: {e}"}), 500


# ── Upload and analyze ────────────────────────────────────────────────────────

@app.route("/api/upload_and_analyze", methods=["POST"])
def upload_and_analyze():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No filename"}), 400

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / filename
    file.save(str(path))

    try:
        size_str = _format_filesize(path.stat().st_size)
        with Image.open(path) as img:
            w, h = img.size
        dims = f"{w} \u00d7 {h}"
    except Exception:
        size_str, dims = "", ""

    try:
        result = _run_analysis_pipeline(path)
        return jsonify({"filename": filename, "filesize": size_str, "dims": dims, **result})
    except Exception as e:
        logger.exception("upload_and_analyze failed for %s", filename)
        return jsonify({"error": f"Analysis failed: {e}"}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if _supabase:
        print("  Using Supabase database.")
    else:
        print("  SUPABASE_URL/KEY not set — falling back to local records.json.")
        if not DATA_FILE.exists():
            candidates = sorted(BASE.glob("ai_image_records_*.json"))
            if candidates:
                seed = candidates[-1]
                DATA_FILE.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")
                print(f"  Seeded records.json from {seed.name}")
            else:
                DATA_FILE.write_text("[]", encoding="utf-8")

    port = int(os.environ.get("PORT", 5000))
    print(f"\n  CSAFE Tracker running → http://localhost:{port}\n")
    app.run(debug=True, port=port)
