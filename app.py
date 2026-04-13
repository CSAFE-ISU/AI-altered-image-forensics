"""
CSAFE AI Image Alteration Tracker — local Flask server.

Usage:
    pip install flask
    python app.py

Then open http://localhost:5000 in your browser.

Records are stored in records.json (next to this file).
Images are searched recursively in 'real images/' and 'altered images/'.
"""

import json
import pathlib
import re
import shutil

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

    print("\n  CSAFE Tracker running → http://localhost:5000\n")
    app.run(debug=True, port=5000)
