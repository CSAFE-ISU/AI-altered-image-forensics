"""
Retroactively run exiftool on every image in the database and save the
raw tag output as JSON to the metadata/ folder.

Usage:
    python backfill_metadata.py [--dry-run] [--overwrite]
"""

import argparse
import json
import os
import pathlib
import sys

from dotenv import load_dotenv

load_dotenv()

BASE = pathlib.Path(__file__).parent
METADATA_DIR = BASE / "metadata"

sys.path.insert(0, str(BASE))
from app import find_image, _run_exiftool  # noqa: E402


def get_filename(rec):
    rtype = rec.get("type", "")
    if rtype == "p0":
        return rec.get("renamed_filename") or rec.get("original_filename")
    if rtype == "p1":
        return rec.get("mod_filename")
    if rtype == "p2":
        return rec.get("altered_filename") or rec.get("ai_assigned_filename")
    if rtype == "p3":
        return rec.get("uploaded_filename")
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Save exiftool metadata for all images in the database."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be saved without writing.",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing metadata files."
    )
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        sys.exit("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")

    from supabase import create_client

    sb = create_client(url, key)

    print("Fetching records from Supabase…")
    rows = sb.table("records").select("id, data").execute().data
    print(f"  {len(rows)} total records")

    METADATA_DIR.mkdir(exist_ok=True)

    saved = skipped = errors = 0

    for row in rows:
        rec = row.get("data") or {}
        rec_id = row["id"]

        filename = get_filename(rec)
        if not filename:
            print(f"  [SKIP] {rec_id} — no filename (type={rec.get('type')})")
            skipped += 1
            continue

        meta_path = METADATA_DIR / (pathlib.Path(filename).stem + ".json")

        if meta_path.exists() and not args.overwrite:
            print(f"  [SKIP] {filename} — metadata already exists")
            skipped += 1
            continue

        path = find_image(filename)
        if not path:
            print(f"  [SKIP] {filename} — file not found on disk")
            skipped += 1
            continue

        tags = _run_exiftool(path)
        if not tags:
            print(f"  [ERROR] {filename} — exiftool returned no data")
            errors += 1
            continue

        print(f"  [SAVE] {filename} → {meta_path.name}")
        if not args.dry_run:
            meta_path.write_text(json.dumps(tags, indent=2))

        saved += 1

    print()
    if args.dry_run:
        print(f"Dry run — {saved} would be saved, {skipped} skipped, {errors} errors.")
    else:
        print(f"Done — {saved} saved, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    main()
