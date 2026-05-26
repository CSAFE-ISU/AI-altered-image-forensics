"""
CSAFE AI Image Alteration Tracker — local Flask server.

Usage:
    python3 -m venv .venv
    source .venv/bin/activate
    pip3 install -r requirements.txt
    PORT=5001 python3 app.py

Then open http://localhost:5001 in your browser.

Records are stored in a shared Supabase database. Copy .env.example to .env
and fill in your SUPABASE_URL and SUPABASE_KEY. Falls back to a local
records.json file if those variables are not set (useful for offline dev).

Images are searched recursively in 'real images/' and 'altered images/'.
"""

import json
import logging
import os
import pathlib
import random
import re
import shutil

import numpy as np
from PIL import Image
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_file

from analysis import _run_analysis_pipeline
from classifier import (
    _RF_FEATURES,
    _RF_FEATURE_LABELS,
    _INDICATOR_FEATURES,
    _extract_indicator_vals,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

app = Flask(__name__, static_folder=str(BASE / "static"))


@app.errorhandler(404)
def not_found(e):
    return jsonify(error=str(e)), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify(error="Internal server error"), 500


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
    """Serve the single-page tracker UI."""
    html = BASE / "tracker.html"
    if not html.exists():
        abort(404, "tracker.html not found next to app.py")
    return html.read_text(encoding="utf-8")


@app.route("/api/records", methods=["GET"])
def get_records():
    """Return all records from Supabase (or local records.json fallback)."""
    if _supabase:
        try:
            result = _supabase.table("records").select("data").execute()
            records = [row["data"] for row in result.data]
            for r in records:
                r.pop(
                    "ela_image_b64", None
                )  # strip legacy records that were stored before write-time stripping
            return jsonify(records)
        except Exception as e:
            return jsonify({"error": str(e)}), 503
    if DATA_FILE.exists():
        return jsonify(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    return jsonify([])


@app.route("/api/records/<record_id>", methods=["POST"])
def set_record(record_id: str):
    """Upsert a single record by ID, stripping the ELA image before storing."""
    rec = request.get_json(force=True)
    if not isinstance(rec, dict):
        return jsonify({"error": "expected a JSON object"}), 400
    if _supabase:
        try:
            storable = {k: v for k, v in rec.items() if k != "ela_image_b64"}
            _supabase.table("records").upsert(
                {"id": record_id, "data": storable}
            ).execute()
        except Exception as e:
            return jsonify({"error": str(e)}), 503
        return jsonify({"ok": True, "id": record_id})
    if DATA_FILE.exists():
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        data = [r for r in data if r.get("id") != record_id]
    else:
        data = []
    data.append(rec)
    DATA_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return jsonify({"ok": True, "id": record_id})


@app.route("/api/records/<record_id>", methods=["DELETE"])
def delete_record(record_id: str):
    """Delete a single record by ID."""
    if _supabase:
        _supabase.table("records").delete().eq("id", record_id).execute()
    else:
        if DATA_FILE.exists():
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            data = [r for r in data if r.get("id") != record_id]
            DATA_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
    return jsonify({"ok": True, "id": record_id})


@app.route("/images/<path:filename>")
def serve_image(filename: str):
    """Locate an image by filename across all IMAGE_ROOTS and serve it."""
    path = find_image(filename)
    if path is None:
        abort(404)
    return send_file(path)


# ── Model / file discovery ────────────────────────────────────────────────────


def find_model_folder(model: str) -> pathlib.Path | None:
    """Return the subfolder of 'altered images/' whose name matches model
    (case-insensitive)."""
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
    """Return a sorted list of AI model names (subdirectories of 'altered images/')."""
    altered_root = BASE / "altered images"
    if not altered_root.exists():
        return jsonify([])
    models = sorted(
        d.name
        for d in altered_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )
    return jsonify(models)


def _format_filesize(size_bytes: int) -> str:
    """Format a byte count as a human-readable string (e.g. '2.4 MB', '830.0 KB')."""
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.1f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.1f} KB"
    return f"{size_bytes} B"


@app.route("/api/original_image_info")
def original_image_info():
    """Return filesize and pixel dimensions for an original or modified image."""
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
    """Return pixel format and dimensions for a file in
    'altered images/<model>/downloaded/'."""
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


@app.route("/api/input_images")
def get_input_images():
    """Return original-renamed and modified images grouped by type."""
    orig_dir = BASE / "real images" / "02-original-renamed"
    mod_dir = BASE / "real images" / "03-modified"

    def list_files(d):
        if not d.is_dir():
            return []
        return sorted(
            f.name for f in d.iterdir() if f.is_file() and not f.name.startswith(".")
        )

    return jsonify({"original": list_files(orig_dir), "modified": list_files(mod_dir)})


# ── Rename helpers ────────────────────────────────────────────────────────────


def _compute_renamed(
    input_image: str, ai_filename: str, model: str
) -> tuple[str, bool]:
    """Return (dest_filename, already_exists).

    dest_filename follows the pattern  <input_stem>-b<NNN>.<ai_ext>  where NNN
    is the next unused three-digit sequence number, searched globally across
    all  altered images/*/renamed/  folders.
    """
    stem = input_image.rsplit(".", 1)[0] if "." in input_image else input_image
    ai_ext = ("." + ai_filename.rsplit(".", 1)[1]) if "." in ai_filename else ""

    # Find the highest existing sequence number for this stem (any extension).
    pattern = re.compile(r"^" + re.escape(stem) + r"-b(\d+)\.[^.]+$", re.IGNORECASE)
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
    """HTTP wrapper for _compute_renamed — previews the destination filename
    without copying the file."""
    input_image = request.args.get("input_image", "").strip()
    ai_filename = request.args.get("ai_filename", "").strip()
    model = request.args.get("model", "").strip()
    if not (input_image and ai_filename and model):
        return jsonify({"error": "Missing required parameters"}), 400
    filename, already_exists = _compute_renamed(input_image, ai_filename, model)
    return jsonify({"filename": filename, "already_exists": already_exists})


@app.route("/api/copy_rename_image", methods=["POST"])
def copy_rename_image():
    """Copy an AI-generated image from downloaded/ to renamed/ with the next
    sequential b-number filename."""
    data = request.get_json(force=True)
    input_image = (data.get("input_image") or "").strip()
    ai_filename = (data.get("ai_filename") or "").strip()
    model = (data.get("model") or "").strip()
    if not (input_image and ai_filename and model):
        return jsonify({"error": "Missing required parameters"}), 400

    dest_filename, already_exists = _compute_renamed(input_image, ai_filename, model)

    if already_exists:
        return jsonify(
            {
                "ok": False,
                "warning": f"File already exists: {dest_filename}",
                "filename": dest_filename,
            }
        )

    model_dir = find_model_folder(model)
    if not model_dir:
        return jsonify({"error": f"Model folder not found for: {model}"}), 404

    src_path = model_dir / "downloaded" / ai_filename
    if not src_path.is_file():
        return (
            jsonify(
                {
                    "error": (
                        f"Source file not found: "
                        f"{model_dir.name}/downloaded/{ai_filename}"
                    )
                }
            ),
            404,
        )

    dest_dir = model_dir / "renamed"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest_dir / dest_filename)

    return jsonify({"ok": True, "filename": dest_filename})


# ── Original image rename helpers ────────────────────────────────────────────

ORIG_SRC_DIR = BASE / "real images" / "01-original"
ORIG_DEST_DIR = BASE / "real images" / "02-original-renamed"


def _compute_original_renamed(
    original_filename: str, study_id: str
) -> tuple[str, bool]:
    """Return (dest_filename, already_exists) for an original image rename.

    dest_filename is  <study_id>.<original_ext>  (e.g. csafe-001.jpg).
    already_exists is True if that file is already present in 02-original-renamed/.
    """
    ext = (
        ("." + original_filename.rsplit(".", 1)[1]) if "." in original_filename else ""
    )
    dest_filename = f"{study_id}{ext}"
    dest_path = ORIG_DEST_DIR / dest_filename
    return dest_filename, dest_path.exists()


@app.route("/api/compute_original_renamed")
def compute_original_renamed_route():
    """HTTP wrapper for _compute_original_renamed — previews the destination
    filename without copying the file."""
    original_filename = request.args.get("original_filename", "").strip()
    study_id = request.args.get("study_id", "").strip()
    if not (original_filename and study_id):
        return jsonify({"error": "Missing required parameters"}), 400
    filename, already_exists = _compute_original_renamed(original_filename, study_id)
    return jsonify({"filename": filename, "already_exists": already_exists})


@app.route("/api/copy_rename_original", methods=["POST"])
def copy_rename_original():
    """Copy an original image from 01-original/ to 02-original-renamed/
    using the study ID as the filename."""
    data = request.get_json(force=True)
    original_filename = (data.get("original_filename") or "").strip()
    study_id = (data.get("study_id") or "").strip()
    if not (original_filename and study_id):
        return jsonify({"error": "Missing required parameters"}), 400

    dest_filename, already_exists = _compute_original_renamed(
        original_filename, study_id
    )

    if already_exists:
        return jsonify(
            {
                "ok": False,
                "warning": f"File already exists: {dest_filename}",
                "filename": dest_filename,
            }
        )

    src_path = ORIG_SRC_DIR / original_filename
    if not src_path.is_file():
        return (
            jsonify(
                {"error": f"Source file not found: 01-original/{original_filename}"}
            ),
            404,
        )

    ORIG_DEST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, ORIG_DEST_DIR / dest_filename)

    return jsonify({"ok": True, "filename": dest_filename})


MOD_DIR = BASE / "real images" / "03-modified"


@app.route("/api/upload_original", methods=["POST"])
def upload_original():
    """Save an uploaded file to 'real images/01-original/'."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    filename = secure_filename(f.filename)
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400
    ORIG_SRC_DIR.mkdir(parents=True, exist_ok=True)
    dest = ORIG_SRC_DIR / filename
    f.save(str(dest))
    return jsonify({"ok": True, "filename": filename})


@app.route("/api/upload_modified", methods=["POST"])
def upload_modified():
    """Save an uploaded modified image to 'real images/03-modified/',
    optionally renaming it via dest_filename."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    f_filename = secure_filename(f.filename)
    dest_filename = (request.form.get("dest_filename") or f_filename).strip()
    if not dest_filename:
        return jsonify({"error": "Invalid filename"}), 400
    MOD_DIR.mkdir(parents=True, exist_ok=True)
    dest = MOD_DIR / dest_filename
    if dest.exists():
        return jsonify(
            {
                "ok": False,
                "warning": f"File already exists: {dest_filename}",
                "filename": dest_filename,
            }
        )
    f.save(str(dest))
    return jsonify({"ok": True, "filename": dest_filename})


@app.route("/api/upload_downloaded", methods=["POST"])
def upload_downloaded():
    """Save an AI-generated image to 'altered images/<model>/downloaded/'."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
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


# ── Random Forest classifier ──────────────────────────────────────────────────


@app.route("/api/random_forest", methods=["POST"])
def random_forest_analysis():
    """Train and cross-validate a Random Forest classifier on analyzed records.

    Accepts optional JSON body fields: models (list to filter altered images),
    stratify_by ('class' or 'model'), feature_set ('pixel', 'indicators', or 'both'),
    and seed (int). Returns fold accuracies, confusion matrix, and feature importances.
    """
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import StratifiedKFold
        from sklearn.metrics import accuracy_score, confusion_matrix as sk_cm
    except ImportError:
        return (
            jsonify(
                {"error": "scikit-learn not installed — run: pip3 install scikit-learn"}
            ),
            503,
        )

    body = request.get_json(force=True) or {}
    selected_models = body.get("models")  # None = all; list = filter p2
    stratify_by = body.get("stratify_by", "class")  # "class" or "model"
    feature_set = body.get("feature_set", "pixel")  # "pixel", "indicators", "both"
    seed_param = body.get("seed")  # int or None (auto)
    seed = int(seed_param) if seed_param is not None else random.randint(0, 2**31 - 1)

    if _supabase:
        rows = _supabase.table("records").select("data").execute().data
        records = [row["data"] for row in rows]
    elif DATA_FILE.exists():
        records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    else:
        return jsonify({"error": "No data available"}), 503

    N_SPLITS = 5

    # Determine feature names for this run
    feature_names = []
    if feature_set in ("pixel", "both"):
        feature_names += _RF_FEATURES + ["ela_source_png"]
    if feature_set in ("indicators", "both"):
        feature_names += _INDICATOR_FEATURES

    X_rows, y, used_recs = [], [], []
    for rec in records:
        rtype = rec.get("type")
        if rtype == "p2":
            if selected_models is not None and rec.get("model") not in selected_models:
                continue
        elif rtype != "p0":
            continue

        row = []
        if feature_set in ("pixel", "both"):
            pixel_vals = [rec.get(f) for f in _RF_FEATURES]
            if any(v is None for v in pixel_vals):
                continue
            row += pixel_vals + [1 if rec.get("ela_source") == "png" else 0]

        if feature_set in ("indicators", "both"):
            ind_vals = _extract_indicator_vals(rec)
            if ind_vals is None:
                continue
            row += ind_vals

        X_rows.append(row)
        y.append(0 if rtype == "p0" else 1)
        used_recs.append(rec)

    if len(X_rows) < 10:
        return jsonify({"error": "Not enough analyzed records to run classifier"}), 422

    X = np.array(X_rows)
    y = np.array(y)

    # Build strata for CV splitting
    if stratify_by == "model":
        model_freq = {}
        for rec in used_recs:
            if rec.get("type") == "p2":
                m = (rec.get("model") or "").strip()
                model_freq[m] = model_freq.get(m, 0) + 1
        individual_strata = sorted(m for m, c in model_freq.items() if c >= N_SPLITS)
        grouped_models = sorted(m for m, c in model_freq.items() if c < N_SPLITS)
        individual_set = set(individual_strata)
        strata = np.array(
            [
                (
                    "original"
                    if rec.get("type") == "p0"
                    else (
                        (rec.get("model") or "").strip()
                        if (rec.get("model") or "").strip() in individual_set
                        else "_other"
                    )
                )
                for rec in used_recs
            ]
        )
    else:
        strata = y
        individual_strata = []
        grouped_models = []

    clf = RandomForestClassifier(
        n_estimators=500, random_state=seed, class_weight="balanced"
    )
    cv = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed)

    fold_accs = []
    y_pred = np.empty_like(y)
    for train_idx, test_idx in cv.split(X, strata):
        clf.fit(X[train_idx], y[train_idx])
        y_pred[test_idx] = clf.predict(X[test_idx])
        fold_accs.append(float(accuracy_score(y[test_idx], y_pred[test_idx])))

    cm = sk_cm(y, y_pred).tolist()

    clf.fit(X, y)
    importances = [
        {
            "feature": n,
            "label": _RF_FEATURE_LABELS.get(n, n),
            "importance": round(float(imp), 4),
        }
        for n, imp in sorted(
            zip(feature_names, clf.feature_importances_), key=lambda x: -x[1]
        )
    ]

    return jsonify(
        {
            "n_original": int((y == 0).sum()),
            "n_altered": int((y == 1).sum()),
            "n_total": int(len(y)),
            "seed": seed,
            "selected_models": selected_models,
            "feature_set": feature_set,
            "stratify_by": stratify_by,
            "individual_strata": individual_strata,
            "grouped_models": grouped_models,
            "fold_accuracies": [round(a, 4) for a in fold_accs],
            "mean_accuracy": round(float(np.mean(fold_accs)), 4),
            "std_accuracy": round(float(np.std(fold_accs)), 4),
            "confusion_matrix": cm,
            "feature_importances": importances,
        }
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if _supabase:
        print("  Using Supabase database.")
    else:
        print("  SUPABASE_URL/KEY not set — falling back to local records.json.")
        if not DATA_FILE.exists():
            candidates = sorted(BASE.glob("ai_image_records_*.json"))
            if candidates:
                source_file = candidates[-1]
                DATA_FILE.write_text(
                    source_file.read_text(encoding="utf-8"), encoding="utf-8"
                )
                print(f"  Seeded records.json from {source_file.name}")
            else:
                DATA_FILE.write_text("[]", encoding="utf-8")

    port = int(os.environ.get("PORT", 5001))
    print(f"\n  CSAFE Tracker running → http://localhost:{port}\n")
    app.run(debug=True, port=port)
