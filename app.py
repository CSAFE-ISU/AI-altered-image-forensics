"""
CSAFE AI Image Alteration Tracker — local Flask server.

Usage:
    pip install flask
    python app.py

Then open http://localhost:5000 in your browser.

Records are stored in records.json (next to this file).
Images are searched recursively in 'real images/' and 'altered images/'.
"""

import base64
import io
import json
import pathlib
import re
import shutil
import subprocess

from flask import Flask, abort, jsonify, request, send_file

BASE = pathlib.Path(__file__).parent
DATA_FILE = BASE / "records.json"

# All directories that may contain images.
IMAGE_ROOTS = [
    BASE / "real images",
    BASE / "altered images",
]

app = Flask(__name__, static_folder=None)


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
    if DATA_FILE.exists():
        return jsonify(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    return jsonify([])


@app.route("/api/records", methods=["POST"])
def set_records():
    data = request.get_json(force=True)
    if not isinstance(data, list):
        return jsonify({"error": "expected a JSON array"}), 400
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return jsonify({"ok": True, "count": len(data)})


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


@app.route("/api/original_image_info")
def original_image_info():
    filename = request.args.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "Missing filename"}), 400
    path = find_image(filename)
    if not path:
        return jsonify({"error": "File not found"}), 404
    try:
        from PIL import Image
        size_bytes = path.stat().st_size
        if size_bytes >= 1_000_000:
            size_str = f"{size_bytes / 1_000_000:.1f} MB"
        elif size_bytes >= 1_000:
            size_str = f"{size_bytes / 1_000:.1f} KB"
        else:
            size_str = f"{size_bytes} B"
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
        from PIL import Image
        with Image.open(path) as img:
            w, h = img.size
            fmt_map = {"JPEG": "JPEG", "PNG": "PNG", "WEBP": "WebP"}
            fmt = fmt_map.get((img.format or "").upper(), img.format or "")
            return jsonify({"format": fmt, "dimensions": f"{w} \u00d7 {h}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

_EXPECTED_CAMERA_FIELDS = ["Make", "Model", "DateTimeOriginal", "ExifIFD:DateTimeOriginal"]


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


def _diff_metadata(input_tags: dict, altered_tags: dict) -> str:
    """Return a human-readable diff of metadata between input and altered images."""
    lines = []

    input_filtered = {k: v for k, v in input_tags.items() if k not in _SKIP_FIELDS}
    altered_filtered = {k: v for k, v in altered_tags.items() if k not in _SKIP_FIELDS}

    all_keys = sorted(set(input_filtered) | set(altered_filtered))
    added, removed, changed = [], [], []

    for k in all_keys:
        in_val = input_filtered.get(k)
        alt_val = altered_filtered.get(k)
        if in_val is None:
            added.append(f"  {k}: → '{alt_val}'")
        elif alt_val is None:
            removed.append(f"  {k}: '{in_val}' → (absent)")
        elif str(in_val) != str(alt_val):
            changed.append(f"  {k}: '{in_val}' → '{alt_val}'")

    if added:
        lines.append("Added:")
        lines.extend(added)
    if removed:
        lines.append("Removed:")
        lines.extend(removed)
    if changed:
        lines.append("Changed:")
        lines.extend(changed)

    if not lines:
        return "No metadata differences found."
    return "\n".join(lines)


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
        from PIL import Image
        with Image.open(path) as img:
            xmp = img.info.get("xmp", b"")
            if isinstance(xmp, bytes):
                xmp = xmp.decode("utf-8", errors="ignore")
            if "c2pa" in xmp.lower():
                return "Yes — with provenance data"
    except Exception:
        pass

    return "No"


def _run_ela(path: pathlib.Path) -> tuple[bool, int, str]:
    """Run Error Level Analysis. Returns (flagged, max_diff, base64_png)."""
    ELA_QUALITY = 90
    ELA_SCALE = 10
    ELA_THRESHOLD = 15

    try:
        from PIL import Image, ImageChops, ImageEnhance
        import numpy as np

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
        import numpy as np
        from PIL import Image

        with Image.open(path) as img:
            gray = np.array(img.convert("L"), dtype=float)

        h, w = gray.shape
        # Simple high-pass: subtract 3×3 mean.
        from PIL import ImageFilter
        with Image.open(path) as img:
            blurred = np.array(img.convert("L").filter(ImageFilter.BoxBlur(3)), dtype=float)
        hp = gray - blurred

        block_noises = []
        for y in range(0, h - BLOCK_SIZE + 1, BLOCK_SIZE):
            for x in range(0, w - BLOCK_SIZE + 1, BLOCK_SIZE):
                block = hp[y:y + BLOCK_SIZE, x:x + BLOCK_SIZE]
                block_noises.append(float(np.std(block)))

        if not block_noises:
            return False, ""

        noise_std = float(np.std(block_noises))
        flagged = noise_std > THRESHOLD
        note = f"Noise inconsistency: block noise std={noise_std:.2f} (threshold {THRESHOLD})."
        return flagged, note if flagged else ""
    except Exception:
        return False, ""


def _check_compression_blocking(path: pathlib.Path) -> tuple[bool, str]:
    """Detect DCT blocking artifacts in JPEG images."""
    BLOCK_SIZE = 8
    RATIO_THRESHOLD = 1.3

    try:
        from PIL import Image
        import numpy as np

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


@app.route("/api/analyze", methods=["POST"])
def analyze_image():
    data = request.get_json(force=True)
    altered_filename = (data.get("altered_filename") or "").strip()
    model = (data.get("model") or "").strip()
    input_image = (data.get("input_image") or "").strip()

    if not (altered_filename and model):
        return jsonify({"error": "Missing required parameters"}), 400

    # Locate the altered image.
    model_dir = find_model_folder(model)
    if not model_dir:
        return jsonify({"error": f"Model folder not found: {model}"}), 404
    altered_path = model_dir / "renamed" / altered_filename
    if not altered_path.is_file():
        return jsonify({"error": f"Altered image not found: {altered_filename}"}), 404

    # Locate the input (original) image if provided.
    input_path = find_image(input_image) if input_image else None

    # Run all analyses.
    altered_tags = _run_exiftool(altered_path)
    input_tags = _run_exiftool(input_path) if input_path else {}

    exif_anomalies = _analyze_exif(altered_tags) if altered_tags else "(exiftool not available)"
    metadata_diff = _diff_metadata(input_tags, altered_tags) if (input_tags and altered_tags) else "(input image metadata unavailable)"
    c2pa_status = _check_c2pa(altered_path, altered_tags)

    ela_flagged, ela_max_diff, ela_b64 = _run_ela(altered_path)
    noise_flagged, noise_note = _check_noise_inconsistency(altered_path)
    blocking_flagged, blocking_note = _check_compression_blocking(altered_path)

    # Build artifacts list and notes.
    artifacts = []
    artifact_note_parts = []
    if ela_flagged:
        artifacts.append("ELA anomaly")
        artifact_note_parts.append(f"ELA: max pixel diff={ela_max_diff} (threshold 15).")
    if noise_flagged:
        artifacts.append("Noise inconsistency")
        artifact_note_parts.append(noise_note)
    if blocking_flagged:
        artifacts.append("Compression blocking")
        artifact_note_parts.append(blocking_note)

    return jsonify({
        "exif_anomalies": exif_anomalies,
        "c2pa_status": c2pa_status,
        "metadata_diff": metadata_diff,
        "artifacts": artifacts,
        "artifact_notes": "\n".join(artifact_note_parts),
        "ela_image_b64": ela_b64,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Seed records.json from the most recent exported file if it doesn't exist.
    if not DATA_FILE.exists():
        candidates = sorted(BASE.glob("ai_image_records_*.json"))
        if candidates:
            seed = candidates[-1]
            DATA_FILE.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  Seeded records.json from {seed.name}")
        else:
            DATA_FILE.write_text("[]", encoding="utf-8")

    import os
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  CSAFE Tracker running → http://localhost:{port}\n")
    app.run(debug=True, port=port)
