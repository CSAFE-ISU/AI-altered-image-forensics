# CSAFE AI Altered Image Forensics

A dataset and tracking tool for studying how AI image-editing models alter photographs, and how those alterations can be detected. Developed in support of research at the [Center for Statistics and Applications in Forensic Evidence (CSAFE)](https://forensicstats.org/).

The tracking tool is a Flask web app (`app.py` + `tracker.html`) that records information about AI-altered images and runs automated forensic analysis on them. Records are stored in a shared Supabase database and auto-saved on every save action. Supabase is hosted on AWS and accessible from anywhere with an internet connection.

The interface uses a five-color palette on a [Shadcn](https://ui.shadcn.com) base, defined as named CSS variables in `static/tracker.css`: rose-wine `#BD4F6C` (primary actions), burnt-peach `#D7816A` (headings / navigation), lime-cream `#D6EA9A` (the sidebar and positive states), vanilla-custard `#F6E2A2` (the canvas background, with white cards), and ink-black `#0D1F2D` (text). Where light or heading text sits on a strong color, a darker shade of that color is used so the text stays legible. The theme is implemented as plain CSS custom properties in `static/tracker.css` — the app stays vanilla JS/CSS with no build step. The preset's dark palette is included under a `.dark` class for a future light/dark toggle. Each form section is a collapsible Shadcn-style accordion: `initAccordions()` in `static/tracker.js` turns the `.section-card` boxes into clickable, collapsible panels at load (collapsed by default). Each header carries a completion-status dot and left accent bar, updated live by `updateAccordionStatus()`: amber = needs completion (a required field is empty, or the section has fields to fill but nothing entered yet), gray = complete (required fields done, or no fields to fill).


## Setup

1. **Clone the Repository**

   Clone the [GitHub repository](https://github.com/CSAFE-ISU/AI-altered-image-forensics.git) to your computer. The records created with the app are stored in a Supabase database and the images themselves are stored in the GitHub.

2. **Create a Free Supabase Account**

   Go to [supabase.com](https://supabase.com) and create a free account. Ask a team member to add you to the **AI-altered Images** project under **Project Settings → Team**. 


3. **Install Python dependencies**

   Open a terminal and change directories to the AI-altered-image-forensics folder.

   ```bash
   cd path/to/AI-altered-image-forensics
   ```

   Create a virtual environment and install the required Python packages:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip3 install -r requirements.txt
   ```

   > NOTE: On Windows, activate the virtual environment with `.venv\Scripts\activate` instead.

4. **(Optional) Install ExifTool**

   If you want to use the metadata and EXIF features in the tracker app, you will need to install [`exiftool`](https://exiftool.org/). If you don't want to install this app, the tracker app should still work but will not populate the metadata and EXIF fields.
   
5. **Configure Supabase credentials in Python**

   Copy `.env.example` to `.env`:

   ```bash
   cp .env.example .env
   ```

   Then fill in your Supabase credentials in `.env`. You can get these by logging in to [supabase.com](https://supabase.com)
      - Open the **AI-altered Images** project, and go to **Project Settings → Data API**. The API URL is on the Data API tab. Copy and paste the API URL into the SUPABASE_URL field in `.env`. Delete any additional characters after "supabase.co".
      - Go to **Project Settings → API Keys** for the publishable key. Copy and paste the publishable key in the SUPABASE_KEY field in `.env`.

   ```
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_KEY=your-publishable-key
   ```

   To use the **AI or Not** detector (see "Run AI or Not" below), also add an
   `AIORNOT_API_KEY`. Sign up at [aiornot.com](https://www.aiornot.com), open the
   dashboard, and create an API key under the API / Developer section (API access
   requires a plan that includes it). Paste the key into `.env`:

   ```
   AIORNOT_API_KEY=your-aiornot-api-key
   ```

   This key is optional — the rest of the app works without it, but the **Run AI
   or Not** button will report that the key is not set.

6. **Start the app**

   If your terminal is already in the CSAFE-AI-altered-image-forensics folder, activate the virtual environment and launch the app:

   ```bash
   source .venv/bin/activate
   PORT=5001 python3 app.py
   ```

   You need to activate the virtual environment each time you open a new terminal. On Windows, use `.venv\Scripts\activate` instead.


   Open [http://localhost:5001](http://localhost:5001) in a browser.

   > NOTE: Port 5000 is blocked by macOS AirPlay Receiver; use 5001 or any other available port.
   
   > NOTE: Depending on how python is installed on your computer, you might need to call `python` instead of `python3` to launch the app.

   To stop the server, press **Ctrl+C** in the terminal where it is running.


## Using the Tracking Tool

Every new original image is assigned a unique *study ID* with the format `csafe_<###>`. The study ID connects modified and altered images to the original image. Records appear in the left sidebar, grouped by the study IDs*.

> **Unsaved changes:** If you switch to a different record, create a new record, or close/refresh the tab while a form has unsaved changes, the app will warn you before proceeding.

There are three image types:

1. **Original** — an unmodified image file as it came from the camera
2. **Modified** — a copy of an original (or another modification) that has been cropped, rotated, recompressed, or otherwise transformed; scene content is unchanged, except where cropping removes part of the frame
3. **Altered** — an original or modified image whose scene content has been changed, either by an AI model or manually in software such as Photoshop

### Upload an original image

Rename the original image with a unique study ID and record details about the image:

1. Click **+ New original** in the sidebar.
2. Click **Browse…** next to the **Original filename** field and select the image from anywhere on your computer.
   - The app saves a copy of the image in `real images/01-original/` and automatically assigns a unique study ID (`csafe-001`, `csafe-002`, …).
   - A renamed copy is created immediately in `real images/02-original-renamed/` (e.g. `csafe-001.jpg`).
   - If an original image with the same filename already exists in the database, a warning is shown with the matching study ID instead.
3. Optionally, fill in the **Notes** field with a scene description, lighting conditions, and any other relevant context.
4. Click **Save record**.

To run forensic analysis on this image, click the **Analyze** button in the **Analysis results** section at the bottom of the record.

### (Optional) Upload a modified image

If a modified version (cropping, resizing, recompression, etc.) of the original image was created and used as the input for the altered image, upload the modified image:

1. Apply the desired transformation externally (e.g. export at 80% JPEG quality in Preview). The modified image can be saved anywhere on your computer under any filename.
2. Click **+ New modification** in the sidebar.
3. Click **Browse…** next to **Select input image** and select the **source image**, the renamed original or renamed previously modified image from which the new modified image was created.
4. Select the transformation type from **Modification type** (Cropped / Resized / Recompressed / Rotated / Other). The app auto-suggests a modified filename (e.g. `csafe-001-recomp.jpg`); edit the **Modified image filename** field if needed. On the next step, the app with save a copy of the image with this filename.
5. Click **Browse…** next to the **Modified image filename** field and select the modified image that you created. The app saves a renamed copy of the image in `real images/03-modified/`.
6. Describe the transformation in **Modification details** (e.g. `exported in Preview at 80% JPEG quality`).
7. Optionally, add additional context in **Notes**.
8. Click **Save record**.

To run forensic analysis on this image, click the **Analyze** button in the **Analysis results** section at the bottom of the record.

### Upload an AI altered image

Record details about an AI altered image:

1. Generate an altered image using an AI tool or software such as Photoshop. Download or save the image somewhere on your computer with the filename suggested by the AI model or software.
1. Click **+ New alteration** in the sidebar.
2. Click **Browse…** next to **Select input image** and select the *source image*, the renamed original or renamed modified image from which the new altered image was created.
3. Fill in the model details:
   - **Model** — select from the list of software and AI models. The list is populated automatically from the `altered images/` subdirectories.
   - **Version / variant** — if you can find information about the version or setting chosen, record it (e.g. `Grok-2`, `Gemini 2.0 Flash`, `Grok: I chose Quality instead of Speed`)
5. Click **Browse…** next to the **Filename as assigned by AI model** field and select the downloaded or saved altered image. The app copies the image into `altered images/<model>/downloaded/` automatically.
6. The **Your assigned filename** field auto-suggests a new name for the altered image appending  `-b<###>` to the end of the source image's filename. The 3-digit number after the letter b is assigned sequentially per source image (e.g. `csafe-002-b001.png`, `csafe-002-b002.png`, `csafe-001-recomp-b001.png`).
6. Click **Copy and Rename** to create save a renamed copy of the altered image in `altered images/<model>/renamed/`.
8. Set the **Date / time generated** to when the image was produced.
9. Enter the exact text you gave the model in **Prompt text** and select the **Prompt strategy** (Vague / Specific / Adversarial).
10. Describe what was added or changed in **Object added** (e.g. `hammer`, `handgun`, `knife`).
11. Click the area(s) of the image that were modified in the interactive **Region altered** 3×3 grid.
12. Set **Mask / selection used** to Yes or No.
13. Rate the realism of the alteration in **Subjective quality** (1 = poor blend, 5 = convincing).
14. Record any observations about the result or the reason for your subjective quality rating in **Notes**.
14. Click **Save record**.

To run forensic analysis on this image, click the **Analyze** button in the **Analysis results** section at the bottom of the record.

### Browse the gallery

Click **Gallery** in the top bar to open a visual grid of all images, organized by study.

- **Single-click** a thumbnail to view the full image in a lightbox.
- **Hover** over a thumbnail to reveal the **⋯** button. Click it to open an action menu with options that depend on the record type:

| Record type | Options |
|---|---|
| Original | View this record · Add new modification · Add new alteration |
| Modification | View original record · Add new alteration |
| Alteration | View original record |

**View this record / View original record** closes the gallery and selects the record in the sidebar. **Add new modification / Add new alteration** closes the gallery, creates a new record of that type, and pre-selects the source image as the input.

### Analyze an image

Each record has an **Analysis results** section at the bottom. Click **Analyze** to run the full forensic pipeline on the image associated with that record. Results appear immediately and are saved with the record.

| Check | Method | What triggers a flag |
|---|---|---|
| EXIF / metadata anomalies | `exiftool` | Known AI software strings, missing camera fields, absent GPS |
| C2PA / Content Credentials | JUMBF block detection via `exiftool` | Embedded C2PA manifest; shows claim generator, actions, validation status |
| Metadata diff vs. input | `exiftool` on both images | Added / removed / changed fields (only when an input image is known) |
| ELA anomaly | Re-compress at quality=90, pixel diff | Max pixel difference > 15 |
| Noise inconsistency | Block-level noise variance (`numpy`) | Uneven noise across 64×64 blocks |
| Compression blocking | DCT boundary analysis | Visible 8×8 block boundaries (JPEG only) |

### Record responses from AI detectors

The **Analysis results** section also collects responses from third-party AI
detectors:

- **AI or Not** — click **Run AI or Not** to send the image to the
  [AI or Not](https://www.aiornot.com) API (requires `AIORNOT_API_KEY` in
  `.env`). The decision (Likely AI / Likely real), the probabilities for human /
  AI / deepfake, and a per-generator class breakdown (e.g. Flux, GPT-4o, Stable
  Diffusion — which varies per image) are filled in automatically and saved with
  the record.
- **Claude** — paste results from [Claude](https://claude.ai) manually. Record
  the model / version, then pick a question from the **Prompt** dropdown (a fixed
  list of 10 standard questions, e.g. "Has this image been altered with AI?") and
  paste Claude's response. Each image stores a separate response per question, so
  you can switch questions in the dropdown and fill in answers one at a time.

### Dashboard

Click **Dashboard** in the top bar to open aggregate analytics across all records,
organized into collapsible groups:

- **Summary** — record counts, alterations by model, subjective-quality
  distribution, and a quality-by-model scatter plot.
- **AI Indicators** — indicator presence by model, visible-watermark coverage,
  and metadata tags by image type.
- **AI or Not Detector** — analysis of the [AI or Not](https://www.aiornot.com)
  results recorded on each image:
  - **Confusion matrix** — treats "Likely AI" as the positive prediction and
    altered images as the positive ground-truth case, with originals and modified
    images grouped as the negative case. Cells show true/false positives and
    negatives, with the false positive rate and false negative rate below.
  - **Detection rate by model** — for altered images, the share flagged "Likely
    AI" per generating model.
  - **AI probability distribution** — density curves of the AI confidence score,
    overlaid for real (originals + modified) vs. altered images.

  Only records that have AI or Not results contribute; confusion-matrix cells and
  bars are clickable to open the matching images in the gallery.
- **Visual / pixel-level artifacts** — distributions of ELA and noise features.
- **Random Forest Classifier** — train and evaluate a classifier on the pixel
  features.


## File naming conventions

| Pattern | Meaning |
|---|---|
| `csafe-001.jpg` | Renamed original (study ID) |
| `csafe-001-recomp.jpg` | Modification — recompressed |
| `csafe-001-cropped.jpg` | Modification — cropped |
| `csafe-001-recomp-b001.png` | AI alteration — first altered version of the recompressed original |
| `csafe-001-recomp-b002.png` | AI alteration — second altered version |

The `b` suffix stands for "bogus" (i.e. altered). The tracker auto-suggests the next sequential number when you create a new alteration record.


## Adding a new model

The model dropdown in the alteration form is populated automatically from the subdirectories of `altered images/`. To add a new model:

1. Create a folder for the model inside `altered images/`, using a short lowercase name (e.g. `comfyui`):

   ```bash
   mkdir -p "altered images/comfyui/downloaded"
   mkdir -p "altered images/comfyui/renamed"
   ```

2. Commit the new folders to the repository so the model is available to all team members:

   ```bash
   git add "altered images/comfyui"
   git commit -m "Add comfyui model folder"
   git push
   ```

3. Restart the app (or reload the page if it is already running) — the new model will appear in the dropdown automatically.

The `downloaded/` subfolder holds files as downloaded from the AI tool; the `renamed/` subfolder holds the renamed copies created by **Copy and Rename** in the tracker.


## Security

This is a local, single-user research tool with no built-in authentication. A
few precautions keep the shared credentials and external connections safe.

- **Enable Supabase Row Level Security (RLS).** The `SUPABASE_KEY` is the
  publishable **anon** key, which is shared across the team. It is only safe if
  RLS is enabled on the `records` table with appropriate access policies. To set
  this up (a project owner/admin does this once):
  1. In the Supabase dashboard, open **SQL Editor → New query**.
  2. Paste the contents of [`supabase_rls.sql`](supabase_rls.sql) and click
     **Run**. This enables RLS and grants the anon role the four operations the
     app needs (select / insert / update / delete). The script is idempotent, so
     it is safe to re-run.
  3. Verify: the **Database → Tables → `records`** view no longer shows the red
     **"Unrestricted"** badge, and four policies appear under **Authentication →
     Policies**.
  4. Confirm the app can still **load**, **save**, and **delete** records.

  **Never** put the `service_role` key in `.env` — it bypasses RLS entirely.
  Note that RLS is a baseline (least privilege + no other tables exposed); it
  does not protect data from someone who already holds the shared anon key. True
  per-user protection requires per-user logins (Supabase Auth), a possible
  future enhancement.
- **Protect your `.env` file.** It holds your credentials and is already
  gitignored — never commit it. On a shared computer, restrict it to your user:
  ```bash
  chmod 600 .env
  ```
  If a key is ever exposed, rotate it (Supabase: **Project Settings → API
  Keys**; AI or Not: regenerate in your account dashboard).
- **Run locally only.** Start the app on the default `localhost` binding and do
  not expose the port to a network or bind to `0.0.0.0`. The app has no
  authentication, and the **Run AI or Not** button spends real API credits on
  every call.
- **Keep the debugger off.** The app runs with the Flask debugger **disabled**
  by default. Only enable it for local development by setting `FLASK_DEBUG=1`,
  and never with the app reachable from a network — the interactive debugger
  allows arbitrary code execution.
- **AI or Not sends images to a third party.** Clicking **Run AI or Not**
  uploads the image to `api.aiornot.com`. Keep this in mind for sensitive
  material, and review their data-retention policy.
- **Audit dependencies periodically.** Check the pinned packages for known
  vulnerabilities:
  ```bash
  pip3 install pip-audit
  pip-audit
  ```


## Troubleshooting

### "Could not load records" error on startup

Free-tier Supabase projects pause automatically after a period of inactivity. When the project is paused, the app cannot reach the database and shows this error.

To restart the project:

1. Go to [supabase.com](https://supabase.com) and sign in.
2. Open the **AI-altered Images** project.
3. If the project is paused, you will see a banner at the top of the dashboard. Click **Restore project**.
4. Wait a minute or two for the project to fully restart.
5. Reload the app in your browser — records should load normally.

> NOTE: Only a project owner or admin can restore a paused project. If you cannot restore it yourself, ask the team member who owns the project.


## Repository structure

```
.
├── app.py                          # Flask backend
├── tracker.html                    # Single-page frontend
├── .env                            # Supabase credentials (not committed — get from a team member)
├── .env.example                    # Credential template
├── requirements.txt                # Python dependencies
├── supabase_rls.sql                # Row Level Security policies for the records table
├── migrate_to_supabase.py          # One-time migration script (already run)
├── real images/
│   ├── 01-original/                # Files as received from camera
│   ├── 02-original-renamed/        # Renamed copies (csafe-001.jpg, etc.)
│   └── 03-modified/                # Pre-processed versions (recompressed, cropped, etc.)
├── altered images/
│   ├── chatgpt/
│   ├── comfyui/
│   ├── gemini/
│   ├── grok/
│   └── ...
│       ├── downloaded/             # Files as downloaded from the AI tool
│       └── renamed/                # Renamed copies (csafe-001-recomp-b001.png, etc.)
```
