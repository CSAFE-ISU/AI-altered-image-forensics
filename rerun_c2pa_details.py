"""
Backfill c2pa_details for records where c2pa_status indicates "Yes" but
c2pa_details is null.

Preserves all c2pa_viewer_* fields — only c2pa_details is updated.

Usage:
    python rerun_c2pa_details.py [--dry-run]
"""

import argparse
import os
import pathlib
import sys

from dotenv import load_dotenv

load_dotenv()

BASE = pathlib.Path(__file__).parent

# Import extraction helpers directly from app.py so we use the same logic.
sys.path.insert(0, str(BASE))
from app import find_image, _run_exiftool, _extract_c2pa_details  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Backfill c2pa_details for records missing them.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be updated without writing.")
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

    candidates = []
    for row in rows:
        rec = row.get("data") or {}
        status = rec.get("c2pa_status", "")
        if "Yes" in status and not rec.get("c2pa_details"):
            candidates.append((row["id"], rec))

    print(f"  {len(candidates)} record(s) need c2pa_details backfill")

    updated = 0
    skipped = 0
    for rec_id, rec in candidates:
        filename = get_filename(rec)
        if not filename:
            print(f"  [SKIP] {rec_id} — no filename in record (type={rec.get('type')})")
            skipped += 1
            continue
        path = find_image(filename)
        if not path:
            print(f"  [SKIP] {filename} — file not found on disk")
            skipped += 1
            continue

        tags = _run_exiftool(path)
        details = _extract_c2pa_details(tags, path)
        if details is None:
            print(f"  [SKIP] {filename} — could not extract C2PA details (no JUMBF tags, c2patool unavailable)")
            skipped += 1
            continue

        print(f"  [UPDATE] {filename} — claim_generator={details.get('claim_generator')!r}")

        if not args.dry_run:
            updated_rec = dict(rec)
            updated_rec["c2pa_details"] = details
            sb.table("records").upsert({"id": rec_id, "data": updated_rec}).execute()

        updated += 1

    print()
    if args.dry_run:
        print(f"Dry run — {updated} would be updated, {skipped} skipped.")
    else:
        print(f"Done — {updated} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
