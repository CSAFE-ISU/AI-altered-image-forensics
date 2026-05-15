# CSAFE AI Altered Image Forensics

A dataset and tracking tool for studying how AI image-editing models alter photographs, and how those alterations can be detected. Developed in support of research at the [Center for Statistics and Applications in Forensic Evidence (CSAFE)](https://forensicstats.org/).

The tracking tool is a Flask web app (`app.py` + `tracker.html`) that records information about AI-altered images and runs automated forensic analysis on them. Records are stored in a shared Supabase database and auto-saved on every save action. Supabase is hosted on AWS and accessible from anywhere with an internet connection.

## Setup

1. **Clone the Repository**

   The repository is on GitHub: https://github.com/CSAFE-ISU/AI-altered-image-forensics.git. Clone it to your computer.


2. **Install Python dependencies**

   Open a terminal and change directories to the AI-altered-image-forensics folder.

   ```bash
   cd path/to/AI-altered-image-forensics
   ``` 

   Install the required Python packages.

   ```bash
   pip install -r requirements.txt
   ```

3. **Install ExifTool**

   Install [`exiftool`](https://exiftool.org/) for EXIF and metadata extraction.
   

4. **Create a Free Supabase Account**

   Go to [supabase.com](https://supabase.com) and create a free account. Ask a team member to add you to the **AI-altered Images** project under **Project Settings → Team**.


5. **Configure database credentials**

   Copy `.env.example` to `.env`:

   ```bash
   cp .env.example .env
   ```

   Then fill in your Supabase credentials. You can get these by logging in to [supabase.com](https://supabase.com), opening the **AI-altered Images** project, and going to **Project Settings → Data API**. The API URL is on the Data API tab; the Publishable Key is on the API Keys tab.

   ```
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_KEY=your-publishable-key
   ```

6. **Start the app**

   ```bash
   PORT=5001 python3 app.py
   ```

   Then open [http://localhost:5001](http://localhost:5001) in a browser.

   > Port 5000 is blocked by macOS AirPlay Receiver; use 5001 or any other available port.

### External CLI tools

Degrade gracefully if absent:
- [`c2patool`](https://github.com/contentauth/c2patool) — C2PA / Content Credentials inspection

---

## Using the Tracking Tool

Records appear in the left sidebar, grouped by a unique *study ID* assigned to each original image by the app. There are four record types:

1. **Original** — an unmodified image file as it came from the camera
2. **Modified** — a copy of an original (or another modification) that has been cropped, rotated, recompressed, or otherwise transformed; scene content is unchanged, except where cropping removes part of the frame
3. **Altered** — an original or modified image whose scene content has been changed, either by an AI model or manually in software such as Photoshop
4. **Analysis** — forensic analysis results for any image

### Page 0 — Original image

Rename the original image with a unique study ID and record details about the image.

1. Click **+ New original** in the sidebar.
2. Click **Browse…** next to the **Original filename** field and select the image from anywhere on your computer. The app copies it into `real images/01-original/` automatically. The Study ID is auto-assigned (`csafe-001`, `csafe-002`, …) and the renamed filename is auto-suggested (e.g. `csafe-001.jpg`). If the image already exists in the database, a warning is shown with the matching study ID instead.
3. Click **Copy and Rename** to create a renamed copy of the file in `real images/02-original-renamed/`.
4. Optionally, fill in the **Notes** field with a scene description, lighting conditions, and any other relevant context.
5. Click **Save record**.

Any forensic analysis run on this image (see Page 3) will appear in the **Analysis results** collapsible section at the bottom of the page.

---

### Page 1 — Modification

Record any pre-processing applied to the original image before it is fed to an AI model (cropping, resizing, recompression, etc.).

1. Click **+ New modification** in the sidebar.
2. Click **Browse…** next to **Select input image** and select the source image (an original or a previously recorded modification) from your computer.
3. Select the transformation type from **Modification type** (Cropped / Resized / Recompressed / Rotated / Other). The app auto-suggests a modified filename (e.g. `csafe-001-recomp.jpg`); edit the **Modified image filename** field if needed.
4. Apply the desired transformation externally (e.g. export at 80% JPEG quality in Preview).
5. Click **Browse…** next to the **Modified image filename** field and select the transformed file from anywhere on your computer. The app copies it into `real images/03-modified/` automatically, and file size and dimensions are auto-populated.
6. Describe the transformation in **Modification details** (e.g. `exported in Preview at 80% JPEG quality`).
7. Optionally, add additional context in **Notes**.
8. Click **Save record**.

Any forensic analysis run on this image (see Page 3) will appear in the **Analysis results** collapsible section at the bottom of the page.

---

### Page 2 — AI alteration

Record details about an AI altered image.

1. Click **+ New alteration** in the sidebar.
2. Click **Browse…** next to **Select input image** and select the source image (an original or a previously recorded modification) from your computer.
3. Fill in the model details:
   - **Model** — select from the list (Grok / Gemini / Adobe Firefly / Photoshop / ChatGPT / Flux / Stable Diffusion / Other)
   - **Version / variant** — if you can find information about the version or setting chosen, record it (e.g. `Grok-2`, `Gemini 2.0 Flash`, `Grok: I chose Quality instead of Speed`)
4. Generate an altered image using an AI tool or software such as Photoshop.
5. Click **Browse…** next to the **Filename as assigned by AI model** field and select the downloaded altered image from anywhere on your computer. The app copies it into `altered images/<model>/downloaded/` automatically and fills in the AI-assigned filename. The **Your assigned filename** field auto-suggests the input image's name with `-b<###>` appended before the extension, assigned sequentially per input image (e.g. `csafe-002-b001.png`, `csafe-002-b002.png`, `csafe-001-recomp-b001.png`). Edit the suggested filename if needed. (Note: the Browse button is disabled until a model is selected.)
6. Click **Copy and Rename** to create a renamed copy in `altered images/<model>/renamed/`.
7. Output format and dimensions are auto-populated.
8. Set the **Date / time generated** to when the image was produced.
9. Enter the exact text you gave the model in **Prompt text** and select the **Prompt strategy** (Vague / Specific / Adversarial).
10. Describe what was added or changed in **Object added** (e.g. `hammer`, `handgun`, `knife`).
11. Click the area(s) of the image that were modified in the interactive **Region altered** 3×3 grid.
12. Set **Mask / selection used** to Yes or No, and rate the realism of the alteration in **Subjective quality** (1 = poor blend, 5 = convincing).
13. Add any observations about the result in **Notes**.
14. Click **Save record**.

Any forensic analysis run on this image (see Page 3) will appear in the **Analysis results** collapsible section at the bottom of the page.

---

### Page 3 — Analysis

Upload an image and perform basic forensic analysis.

1. Click **+ New analysis** in the sidebar.
2. Click **Choose File** and select the image to analyze.
3. Click **Upload & Analyze**. The app will run the full analysis pipeline and attempt to match the filename against existing records:
   - **Match found** — results are attached to that record and shown in its **Analysis results** section.
   - **No match** — a standalone analysis record is created and listed under **Analyses** in the sidebar.
4. Review the results for each check:

   | Check | Method | What triggers a flag |
   |---|---|---|
   | EXIF / metadata anomalies | `exiftool` | Known AI software strings, missing camera fields, absent GPS |
   | C2PA / Content Credentials | JUMBF block detection via `exiftool` | Embedded C2PA manifest; shows claim generator, actions, validation status |
   | Metadata diff vs. input | `exiftool` on both images | Added / removed / changed fields (only when an input image is known) |
   | ELA anomaly | Re-compress at quality=90, pixel diff | Max pixel difference > 15 |
   | Noise inconsistency | Block-level noise variance (`numpy`) | Uneven noise across 64×64 blocks |
   | Compression blocking | DCT boundary analysis | Visible 8×8 block boundaries (JPEG only) |

5. Click **Save record** to store the analysis results.

---

## File naming conventions

| Pattern | Meaning |
|---|---|
| `csafe-001.jpg` | Renamed original (study ID) |
| `csafe-001-recomp.jpg` | Page 1 modification — recompressed |
| `csafe-001-cropped.jpg` | Page 1 modification — cropped |
| `csafe-001-recomp-b001.png` | Page 2 alteration — first altered version of the recompressed original |
| `csafe-001-recomp-b002.png` | Page 2 alteration — second altered version |

The `b` suffix stands for "bogus" (i.e. altered). The tracker auto-suggests the next sequential number when you create a new Page 2 record.

---

## Repository structure

```
.
├── app.py                          # Flask backend
├── tracker.html                    # Single-page frontend
├── .env                            # Supabase credentials (not committed — get from a team member)
├── .env.example                    # Credential template
├── requirements.txt                # Python dependencies
├── migrate_to_supabase.py          # One-time migration script (already run)
├── real images/
│   ├── 01-original/                # Files as received from camera
│   ├── 02-original-renamed/        # Renamed copies (csafe-001.jpg, etc.)
│   └── 03-modified/                # Pre-processed versions (recompressed, cropped, etc.)
├── altered images/
│   ├── chatgpt/
│   ├── gemini/
│   ├── grok/
│   └── ...
│       ├── downloaded/             # Files as downloaded from the AI tool
│       └── renamed/                # Renamed copies (csafe-001-recomp-b001.png, etc.)
└── analyzed images/                # Images uploaded via Page 3 — Analysis
```
