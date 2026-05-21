"""
Retroactively compute and save forensic indicators for all records in Supabase.
Uses saved metadata JSON files when available; falls back to running exiftool.

Usage:
    python backfill_indicators.py [--dry-run] [--overwrite]
"""

import argparse
import json
import os
import pathlib
import sys

from dotenv import load_dotenv

load_dotenv()

BASE         = pathlib.Path(__file__).parent
METADATA_DIR = BASE / "metadata"

sys.path.insert(0, str(BASE))
from app import find_image, _run_exiftool, _detect_indicators  # noqa: E402


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


def get_tags(filename):
    stem = pathlib.Path(filename).stem
    meta_path = METADATA_DIR / (stem + ".json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    path = find_image(filename)
    if not path:
        return None
    return _run_exiftool(path) or None


def main():
    parser = argparse.ArgumentParser(description="Backfill forensic indicators for all records in Supabase.")
    parser.add_argument("--dry-run",   action="store_true", help="Print what would be updated without writing.")
    parser.add_argument("--overwrite", action="store_true", help="Update records that already have indicators.")
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

    updated = skipped = errors = 0

    for row in rows:
        rec    = row.get("data") or {}
        rec_id = row["id"]

        if not args.overwrite and rec.get("indicators") is not None:
            skipped += 1
            continue

        filename = get_filename(rec)
        if not filename:
            print(f"  [SKIP] {rec_id} — no filename (type={rec.get('type')})")
            skipped += 1
            continue

        tags = get_tags(filename)
        if tags is None:
            print(f"  [ERROR] {filename} — could not get metadata")
            errors += 1
            continue

        indicators = _detect_indicators(tags)
        print(f"  [UPDATE] {filename} — {indicators['summary']}")

        if not args.dry_run:
            updated_rec = dict(rec)
            updated_rec["indicators"] = indicators
            sb.table("records").upsert({"id": rec_id, "data": updated_rec}).execute()

        updated += 1

    print()
    if args.dry_run:
        print(f"Dry run — {updated} would be updated, {skipped} skipped, {errors} errors.")
    else:
        print(f"Done — {updated} updated, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    main()
