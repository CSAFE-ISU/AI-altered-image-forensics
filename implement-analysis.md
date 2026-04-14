# Plan: Automated 2B-Analysis for CSAFE AI Image Tracker

## Context

The 2B-Analysis page requires manual entry of forensic findings for each altered image. Several of these steps can be partially or fully automated: EXIF/metadata extraction, C2PA detection, metadata diffing against the input image, ELA (Error Level Analysis), noise inconsistency, and compression blocking. The goal is to add a "Run Analysis" button to the 2B panel that auto-fills as many fields as possible, saving researcher time and improving consistency.

---

## Critical Files

- `app.py` — Flask backend; add a new route function decorated with `@app.route("/api/analyze", methods=["POST"])` that runs the forensic analysis and returns results as JSON. This follows the same pattern as existing routes like `/api/image_info` and `/api/copy_rename_image` already in this file.
- `tracker.html` — Main UI; add "Run Analysis" button and ELA preview to the 2B panel (`#panel1`, line 614)

---

## What Gets Automated

| Field | Method | Confidence |
|---|---|---|
| EXIF / metadata anomalies | `exiftool` subprocess | Full |
| C2PA / Content Credentials | `c2patool` CLI (with fallback to XMP check via `Pillow`) | Full |
| Metadata diff vs. input | `exiftool` on both images, field-by-field diff | Full |
| ELA anomaly (artifact checkbox) | Re-compress at fixed quality, pixel diff | Full |
| Compression blocking (artifact checkbox) | DCT boundary analysis on JPEG images | Partial |
| Noise inconsistency (artifact checkbox) | Block-level noise variance with `numpy` | Partial |

---

## Implementation Plan

### Step 1 — New Flask endpoint: `POST /api/analyze`

Add to **`app.py`**.

**Request body:**
```json
{
  "altered_filename": "csafe-001-recomp-b001.png",
  "model": "grok",
  "input_image": "csafe-001-recomp.jpeg"
}
```

**Response:**
```json
{
  "exif_anomalies": "Software: 'Adobe Firefly'. No camera make/model. GPS absent.",
  "c2pa_status": "No",
  "metadata_diff": "Added: Software → 'Adobe Firefly'\nRemoved: Make, Model, GPS*\n...",
  "artifacts": ["ELA anomaly"],
  "artifact_notes": "ELA: elevated error in center region (max diff 42). ...",
  "ela_image_b64": "<base64-encoded PNG of ELA visualization>"
}
```

#### Sub-functions to add to `app.py`:

**`_run_exiftool(path)`** — subprocess call to `exiftool -json <path>`, returns dict of tags. Falls back gracefully if exiftool not installed (returns `{}` with a warning).

**`_analyze_exif(altered_tags)`** — scans tag values for known AI software strings (`Adobe Firefly`, `DALL-E`, `Midjourney`, `Stable Diffusion`, `Imagen`, `Grok`, `Gemini`, `ChatGPT`), missing expected camera fields (`Make`, `Model`, `ExifIFD:DateTimeOriginal`), absent GPS. Returns anomaly summary string.

**`_diff_metadata(input_tags, altered_tags)`** — compares two exiftool dicts, returns human-readable summary of added/removed/changed fields (excluding derived/computed fields like file size and thumbnail data).

**`_check_c2pa(path)`** — tries `c2patool --info <path>` subprocess. Parses stdout: if manifest present and non-empty → `"Yes — with provenance data"`, if manifest present but empty → `"Yes — but empty / stripped"`, if absent or tool not found → `"No"`. Falls back to checking for `xmp:c2pa` namespace in XMP data via Pillow if `c2patool` is unavailable.

**`_run_ela(path)`** — PIL-based ELA:
1. Open image, convert to RGB
2. Save to in-memory BytesIO as JPEG at quality=90
3. Reload and compute absolute pixel difference
4. Scale difference ×10 for visibility
5. Return `(flagged: bool, max_diff: int, b64_png: str)`
6. Flag as anomaly if `max_diff > 15` (tunable threshold)

**`_check_noise_inconsistency(path)`** — numpy-based:
1. Convert to grayscale, compute per-64×64-block noise estimate (std of high-pass filtered block)
2. If std of block estimates > threshold → flag "Noise inconsistency"
3. Returns `(flagged: bool, note: str)`

**`_check_compression_blocking(path)`** — JPEG-only:
1. Check if image is JPEG (skip if PNG/WebP)
2. Measure mean absolute difference at 8-pixel horizontal/vertical boundaries vs. interior pixels
3. If blockiness ratio > threshold → flag "Compression blocking"
4. Returns `(flagged: bool, note: str)`

---

### Step 2 — "Run Analysis" button in `tracker.html`

**Location:** Inside `#panel1` (2b panel), above the existing section cards.

**HTML to add** (above the first `section-card` in `#panel1`):
```html
<div class="analyze-bar">
  <button class="btn analyze-btn" id="analyze-btn" onclick="runAnalysis()">
    Run Analysis
  </button>
  <span class="status-msg" id="status-analyze"></span>
</div>
```

**JavaScript `runAnalysis()` function:**
1. Read `altered_filename` from `rec.altered_filename`, `model` from `rec.model`, `input_image` from `rec.input_image`
2. If any are missing, show error in `status-analyze`
3. Disable button, show "Running…"
4. `POST /api/analyze` with JSON body
5. On success:
   - Set `p2_exif` textarea to `exif_anomalies`
   - Set `p2_c2pa` select to `c2pa_status`
   - Set `p2_metadiff` textarea to `metadata_diff`
   - Check the artifact checkboxes matching entries in `artifacts` array
   - Append `artifact_notes` to `p2_artifact_notes` textarea
   - If `ela_image_b64` is present, show it in a collapsible `<details>` element (`#ela-preview`) beneath the artifact grid
6. Show "Analysis complete" in `status-analyze`

**ELA preview HTML** (add inside artifact section):
```html
<details id="ela-preview" style="display:none">
  <summary>ELA visualization</summary>
  <img id="ela-img" style="max-width:100%; margin-top:0.5rem;">
</details>
```

---

### Step 3 — Dependencies

Add to `app.py` imports: `subprocess`, `base64`, `io` (all stdlib).
New pip dependency: `numpy` (for noise analysis).
`exiftool` and `c2patool` are CLI tools installed separately — both degrade gracefully if absent.
`Pillow` is already imported in existing routes.

---

## Reused Patterns

- `find_image(filename)` (`app.py:35`) — locate the input image file
- `find_model_folder(model)` (`app.py:90`) — locate the altered image under `altered images/{model}/renamed/`
- Existing `showStatus(id, msg, type)` JS function in `tracker.html` — button feedback
- Existing `.btn` CSS class — style for the "Run Analysis" button

---

## To-Do Checklist

### Backend (`app.py`)
- [ ] Add `import subprocess`, `import base64`, `import io` at the top
- [ ] Install `numpy`: `pip install numpy`
- [ ] Write `_run_exiftool(path)` — call `exiftool -json`, return tag dict; return `{}` if tool not found
- [ ] Write `_analyze_exif(altered_tags)` — flag AI software strings and missing camera fields
- [ ] Write `_diff_metadata(input_tags, altered_tags)` — field-by-field comparison, return summary string
- [ ] Write `_check_c2pa(path)` — try `c2patool`, fall back to XMP check via Pillow
- [ ] Write `_run_ela(path)` — recompress at quality=90, compute pixel diff, return `(flagged, max_diff, b64_png)`
- [ ] Write `_check_noise_inconsistency(path)` — block-level noise variance with numpy
- [ ] Write `_check_compression_blocking(path)` — DCT boundary analysis for JPEG images
- [ ] Write `POST /api/analyze` route that calls all of the above and returns combined JSON response

### Frontend (`tracker.html`)
- [ ] Add "Run Analysis" button HTML above the first `section-card` in `#panel1` (line 614)
- [ ] Add ELA preview `<details>`/`<img>` HTML inside the artifact section
- [ ] Write `runAnalysis()` JavaScript function that POSTs to `/api/analyze`
- [ ] In `runAnalysis()`: populate `p2_exif`, `p2_c2pa`, `p2_metadiff` fields from response
- [ ] In `runAnalysis()`: check artifact checkboxes matching the `artifacts` array in the response
- [ ] In `runAnalysis()`: populate `p2_artifact_notes` from response
- [ ] In `runAnalysis()`: show ELA image in `#ela-preview` if `ela_image_b64` is present
- [ ] In `runAnalysis()`: show error in `#status-analyze` if required record fields are missing

---

## Verification

1. Start server: `PORT=5001 python3 app.py`
2. Open a p2 record that has `altered_filename`, `model`, and `input_image` filled in
3. Switch to the 2b Analysis tab
4. Click "Run Analysis"
5. Verify:
   - `EXIF / metadata anomalies` field is populated
   - `C2PA` dropdown is set
   - `Metadata diff` field is populated
   - Relevant artifact checkboxes are auto-checked
   - ELA preview image appears (bright areas = potential manipulation)
6. Click "Save record" and confirm fields persist to `records.json`
7. Test graceful degradation: with `exiftool` absent, confirm endpoint returns partial results without crashing
