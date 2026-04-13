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
