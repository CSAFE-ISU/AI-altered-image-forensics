"""
Retroactively compute and save ela_max_diff and block_noise_std for all
analyzed records in Supabase.  Only processes records that already have
artifacts/artifact_notes (i.e. have been through the analysis pipeline).

Usage:
    python backfill_ela_noise.py [--dry-run] [--overwrite]
"""

import argparse
import os
import pathlib
import sys

from dotenv import load_dotenv

load_dotenv()

BASE = pathlib.Path(__file__).parent

sys.path.insert(0, str(BASE))
from app import find_image, _run_ela, _check_noise_inconsistency  # noqa: E402


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
        description="Backfill ela_max_diff and block_noise_std for analyzed records."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be updated without writing.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Update records that already have these fields.",
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

    updated = skipped = errors = 0

    for row in rows:
        rec = row.get("data") or {}
        rec_id = row["id"]

        # Only process records that have been through analysis
        if rec.get("artifacts") is None:
            skipped += 1
            continue

        if not args.overwrite and rec.get("ela_max_diff") is not None:
            skipped += 1
            continue

        filename = get_filename(rec)
        if not filename:
            print(f"  [SKIP] {rec_id} — no filename (type={rec.get('type')})")
            skipped += 1
            continue

        path = find_image(filename)
        if not path:
            print(f"  [ERROR] {filename} — image file not found on disk")
            errors += 1
            continue

        try:
            _, ela_max_diff, _ = _run_ela(path)
            _, noise_std, _ = _check_noise_inconsistency(path)
            print(
                f"  [UPDATE] {filename} — ela_max_diff={ela_max_diff},"
                f" block_noise_std={noise_std:.4f}"
            )

            if not args.dry_run:
                updated_rec = dict(rec)
                updated_rec["ela_max_diff"] = ela_max_diff
                updated_rec["block_noise_std"] = round(noise_std, 4)
                sb.table("records").upsert(
                    {"id": rec_id, "data": updated_rec}
                ).execute()

            updated += 1
        except Exception as e:
            print(f"  [ERROR] {filename} — {e}")
            errors += 1

    print()
    if args.dry_run:
        print(
            f"Dry run — {updated} would be updated, {skipped} skipped, {errors} errors."
        )
    else:
        print(f"Done — {updated} updated, {skipped} skipped, {errors} errors.")


if __name__ == "__main__":
    main()
