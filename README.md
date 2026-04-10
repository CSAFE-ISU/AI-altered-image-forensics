# CSAFE AI Altered Image Forensics

A dataset and tracking tool for studying how AI image-editing models alter photographs, and how those alterations can be detected. Developed in support of research at the [Center for Statistics and Applications in Forensic Evidence (CSAFE)](https://forensicstats.org/).

## The tracking tool
The tracking tool captures information about the creation of an AI-altered image. 
`ai_image_alteration_tracker.html` is a self-contained, single-file web app. Open it in any modern browser — no server, no install, no dependencies.

```
double-click  ai_image_alteration_tracker.html
```

or drag it into a browser window.

### Loading an existing session

Click **Load JSON file** in the bar just below the header and select a previously exported `.json` file (e.g. `ai_image_records_2026-04-10.json`). All records will appear in the left sidebar, grouped by phase.

---

## Record phases

The tracker organises every image into one of three phases, visible in the left sidebar.

### Phase 0 — Original image

Records the unmodified camera file before any processing.

| Field | Description |
|---|---|
| Study ID | Auto-assigned (`csafe-001`, `csafe-002`, …). Ties all derived files together. |
| Original filename | The camera-assigned name (e.g. `iPhone6s-2_Scene-20190630-185705_JPG-00_I100_E30_o.jpg`) |
| File size | e.g. `3.9 MB` |
| Dimensions | e.g. `4032 × 3024` |
| Device / camera | e.g. `iPhone 6s` |
| Notes | Scene description, lighting conditions, any context |

Click **+ New original** in the sidebar to start a Phase 0 record.

---

### Phase 1 — Modification

Records any pre-processing applied to the original before it is fed to an AI model (cropping, resizing, recompression, etc.).

| Field | Description |
|---|---|
| Input image | Select from previously recorded originals or modifications |
| Modification type | Cropped / Resized / Recompressed / Rotated / Other |
| Modification details | Free-text description (e.g. `exported in Preview at 80% JPEG quality`) |
| File size after | e.g. `1.5 MB` |
| Dimensions after | e.g. `4032 × 3024` |
| Modified filename | Auto-suggested from the study ID and modification type; editable |
| Notes | Any other details |

The suggested filename follows the pattern `csafe-001-recomp.jpg`, `csafe-001-cropped.jpg`, etc.

Click **+ New modification** in the sidebar to start a Phase 1 record.

---

### Phase 2 — AI alteration + analysis

The most detailed phase. Each record documents one AI-generated alteration and (optionally) a forensic analysis of that output. The form has two tabs.

#### Tab 2a — Alteration

| Field | Description |
|---|---|
| Input image | Select from recorded originals and modifications |
| Model | Grok / Gemini / Adobe Firefly / Photoshop / ChatGPT / Flux / Stable Diffusion / Other |
| Version / variant | e.g. `Black Forest Labs FLUX.2 Max`, `ChatGPT Plus — Instant` |
| Prompt text | Exact prompt given to the model |
| Prompt strategy | Vague / Specific / Adversarial |
| Object added | e.g. `hammer`, `handgun`, `knife` |
| Region altered | Grid position: top-left … bottom-right |
| Mask / selection used | User-defined mask / free-form inpainting / bounding box |
| AI-assigned filename | The filename the model gave the download (e.g. `grok-image-8e38d268.png`) |
| Your assigned filename | Auto-suggested from study ID and a sequential alteration number (`csafe-001-recomp-b001.png`); editable |
| Output format | JPEG / PNG / WebP / Other |
| Output dimensions | e.g. `1168 × 680` |
| Date / time generated | Datetime picker |
| Subjective quality | 1 (poor blend) – 5 (convincing) |
| Notes | Observations about the alteration |

#### Tab 2b — Analysis

Fill this tab after examining the altered image with forensic tools.

**Metadata forensics**

| Field | Description |
|---|---|
| EXIF / metadata anomalies | e.g. `GPS stripped`, `Software tag reads "Adobe Firefly"` |
| C2PA / Content Credentials | Yes with provenance / Yes but stripped / No |
| Metadata diff vs. input | Summary of fields that changed |

**Visual / pixel-level artifacts**

Check all artifacts observed in the image:

- ELA anomaly
- Blending seam visible
- Noise inconsistency
- Lighting mismatch
- Shadow mismatch
- Perspective mismatch
- Compression blocking
- Color fringing
- Clone/copy artifacts
- None visible

Add free-text artifact notes for location, severity, or unlisted artifacts.

**AI detector results**

Add one row per detector tool. Each row captures:
- Detector name + version
- Confidence score
- Verdict (Real / Uncertain / AI-generated)

Also record baseline results — the same detectors run on the unaltered input image — for comparison.

**Overall analysis notes**

Summary findings, anomalies worth flagging, open questions.

Click **+ New alteration** in the sidebar to start a Phase 2 record.

---

## Saving and exporting

- **Save record** — writes the current form fields back into the in-memory record list and confirms with a green status message. Records are not written to disk until you export.
- **Clear fields** — resets the visible form without deleting the record.
- **Delete record** — permanently removes the record from the session.
- **Export all records** (top-right header button) — downloads the full record list as a JSON file named `ai_image_records_YYYY-MM-DD.json`. Keep this file alongside the images in the repository.

> **Important:** the tracker runs entirely in the browser. If you close the tab without exporting, unsaved changes are lost. Export often.

---

## File naming conventions

| Pattern | Meaning |
|---|---|
| `csafe-001.jpg` | Study ID — renamed original |
| `csafe-001-recomp.jpg` | Phase 1 modification — recompressed |
| `csafe-001-cropped.jpg` | Phase 1 modification — cropped |
| `csafe-001-recomp-b001.png` | Phase 2 alteration — first altered version of the recompressed original |
| `csafe-001-recomp-b002.png` | Phase 2 alteration — second altered version |

The `b` suffix stands for "bogus" (i.e. altered). The tracker auto-suggests the next sequential number when you create a new Phase 2 record.

## Repository structure

```
.
├── ai_image_alteration_tracker.html   # Standalone data-entry form (no install needed)
├── ai_image_records_YYYY-MM-DD.json   # Exported record data
├── real images/
│   ├── 01-original/                   # Files as received from camera
│   ├── 02-original-renamed/           # Same files with study-ID names (e.g. csafe-001.jpg)
│   └── 03-modified/                   # Pre-processed versions (recompressed, cropped, etc.)
└── altered images/
    ├── chatgpt/
    ├── deevid/
    ├── flux/
    ├── gemini/
    ├── grok/
    └── stablediffusionweb/
        ├── downloaded/                # Files as downloaded from the AI tool
        └── renamed/                   # Same files with study-ID names (e.g. csafe-001-recomp-b008.png)
```
