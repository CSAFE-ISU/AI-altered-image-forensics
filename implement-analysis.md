# Automated Forensic Analysis — CSAFE AI Image Tracker

## Summary

Automated forensic analysis is fully implemented. Analysis can be run on any image (not just AI-altered ones) via the **Page 3 — Analysis** view. Results are displayed in a read-only "Analysis results" collapsible section at the bottom of every record form (p0, p1, p2).

---

## What Gets Automated

| Field | Method | Confidence |
|---|---|---|
| EXIF / metadata anomalies | `exiftool` subprocess | Full |
| C2PA / Content Credentials | JUMBF block detection via `exiftool` tags | Full |
| C2PA provenance details | CBOR tag parsing (claim generator, actions, validation) | Full |
| Metadata diff vs. input | `exiftool` on both images, field-by-field diff | Full |
| ELA anomaly | Re-compress at quality=90, pixel diff | Full |
| Compression blocking | DCT boundary analysis on JPEG images | Partial |
| Noise inconsistency | Block-level noise variance with `numpy` | Partial |

---

## Architecture

### Backend (`app.py`)

**Helper functions:**

- **`_run_exiftool(path)`** — subprocess call to `exiftool -json -a -G1 <path>`, returns tag dict. Returns `{}` gracefully if exiftool not installed.
- **`_analyze_exif(tags)`** — flags known AI software strings (`Adobe Firefly`, `DALL-E`, `Midjourney`, `Stable Diffusion`, `Imagen`, `Grok`, `Gemini`, `ChatGPT`), missing camera fields (`Make`, `Model`, `DateTimeOriginal`), absent GPS. Skips file path fields to avoid false positives.
- **`_diff_metadata(input_tags, altered_tags)`** — field-by-field comparison, returns human-readable summary of added/removed/changed fields, excluding derived fields (file size, thumbnail data, etc.).
- **`_check_c2pa(path, tags)`** — detects C2PA credentials by scanning exiftool tags for JUMBF blocks containing `"c2pa"`. Falls back to XMP check if no JUMBF found.
- **`_extract_c2pa_details(tags)`** — parses CBOR tags to extract claim generator, software agent, C2PA version, actions, digital source type, manifest ID, and validation failures.
- **`_run_ela(path)`** — PIL-based ELA: re-compress at quality=90, compute absolute pixel diff, scale ×10. Returns `(flagged: bool, max_diff: int, b64_png: str)`. Flags if `max_diff > 15`.
- **`_check_noise_inconsistency(path)`** — per-64×64-block noise estimate; flags if std of block estimates exceeds threshold. Returns `(flagged: bool, note: str)`.
- **`_check_compression_blocking(path)`** — JPEG-only; measures mean absolute difference at 8-pixel boundaries vs. interior pixels. Returns `(flagged: bool, note: str)`.

**Endpoints:**

- **`POST /api/analyze`** — runs analysis on a named altered image (used internally; kept for backwards compatibility). Takes `{altered_filename, model, input_image}`.
- **`POST /api/upload_and_analyze`** — accepts `multipart/form-data` with a `file` field. Saves to `uploaded images/`, runs the full pipeline, returns JSON with all analysis fields. No metadata diff (no input image to compare against).

### Frontend (`tracker.html`)

**Page 3 — Analysis:**
- `+ New analysis` button in the sidebar opens the upload form
- `uploadAndAnalyze()` POSTs to `/api/upload_and_analyze`
- Filename is matched client-side against all record fields (`original_filename`, `mod_filename`, `altered_filename`, `ai_assigned_filename`, `uploaded_filename`)
- **Match found:** analysis is attached to the existing record; user is navigated to it
- **No match:** a new standalone `p3` record is created and appears in an "Analyses" section at the bottom of the sidebar

**Shared "Analysis results" section (p0, p1, p2 forms):**
- Collapsible `<details>` at the bottom of each form, above the Save button
- Read-only; populated by `fillAnalysisSection(prefix, rec)` when a record is loaded
- Shows empty-state message ("Run analyses by clicking New Analysis in the sidebar") if no analysis data exists
- Displays: EXIF anomalies, C2PA status, C2PA details table, metadata diff, artifact tags, artifact notes, ELA visualization

**Key JS functions:**
- `newAnalysis()` — creates a blank p3 record and shows the upload form
- `uploadAndAnalyze()` — handles file upload, response parsing, match/create logic
- `fillAnalysisSection(prefix, rec)` — populates the shared analysis section for p0/p1/p2
- `fillP3(rec)` — populates the Page 3 form for saved p3 records

### p3 Record Schema

```json
{
  "id": "rec_1234567890",
  "type": "p3",
  "uploaded_filename": "mystery.png",
  "filesize": "2.1 MB",
  "dims": "1536 × 1024",
  "uploaded_at": "2026-04-14T10:30:00",
  "exif_anomalies": "...",
  "c2pa_status": "No",
  "c2pa_details": null,
  "metadata_diff": "",
  "artifacts": ["ELA anomaly"],
  "artifact_notes": "...",
  "ela_image_b64": "<base64>",
  "linked_record": "",
  "analysis_notes": ""
}
```

Analysis fields (`exif_anomalies`, `c2pa_status`, `c2pa_details`, `metadata_diff`, `artifacts`, `artifact_notes`, `ela_image_b64`) are stored directly on p0/p1/p2 records when analysis is linked to an existing record.

---

## Dependencies

- **`exiftool`** — CLI, installed separately. Degrades gracefully if absent.
- **`numpy`** — pip package, used for noise inconsistency analysis.
- **`Pillow`** — already a project dependency; used for ELA and image info.
- `subprocess`, `base64`, `io` — stdlib, already imported.

---

## Verification

1. Start server: `PORT=5001 python3 app.py`
2. **Existing image:** click `+ New analysis`, upload an image whose filename matches an existing record → app navigates to that record; "Analysis results" section expands with results
3. **Unknown image:** upload an image with no matching record → new entry appears in "Analyses" sidebar section
4. **Re-select p3 record:** click it in the sidebar → Page 3 loads with previously saved results
5. **p0/p1/p2 with analysis:** select any record that has analysis data → "Analysis results" section auto-expands at the bottom of the form
6. **No analysis yet:** select a record with no analysis data → section shows "Run analyses by clicking New Analysis in the sidebar"
7. **Graceful degradation:** with `exiftool` absent, confirm upload endpoint returns partial results without crashing
