"""
Backfill c2pa_details for records where c2pa_status indicates "Yes" but
c2pa_details is null.

Preserves all c2pa_viewer_* fields — only c2pa_details is updated.

Usage:
    python rerun_c2pa_details.py [--dry-run]
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

BASE = pathlib.Path(__file__).parent

IMAGE_ROOTS = [
    BASE / "real images",
    BASE / "altered images",
    BASE / "analyzed images",
]


def find_image(filename: str) -> pathlib.Path | None:
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


def extract_c2pa_details_from_c2patool(path: pathlib.Path) -> dict | None:
    try:
        result = subprocess.run(
            ["c2patool", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        data = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None

    active_key = data.get("active_manifest")
    manifests  = data.get("manifests", {})
    manifest   = manifests.get(active_key) or (next(iter(manifests.values()), None) if manifests else None)
    if not manifest:
        return None

    sig     = manifest.get("signature_info") or {}
    cg_info = manifest.get("claim_generator_info") or []
    cg_name = cg_info[0].get("name") if cg_info else manifest.get("claim_generator")

    raw_actions = []
    for assertion in manifest.get("assertions") or []:
        if assertion.get("label", "").startswith("c2pa.actions"):
            for a in (assertion.get("data") or {}).get("actions") or []:
                act = a.get("action", "")
                raw_actions.append(act.replace("c2pa.", ""))

    return {
        "claim_generator":     cg_name,
        "software_agent":      sig.get("issuer"),
        "c2pa_version":        None,
        "actions":             raw_actions or None,
        "digital_source_type": None,
        "validation_failures": None,
        "validation_failure_explanations": None,
        "manifest_id":         active_key,
    }


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

    VIEWER_KEYS = {
        "c2pa_viewer_found",
        "c2pa_viewer_signed_by",
        "c2pa_viewer_issued",
        "c2pa_viewer_algorithm",
        "c2pa_viewer_cert_status",
        "c2pa_viewer_software",
        "c2pa_viewer_json",
        "c2pa_viewer_notes",
    }

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
        filename = rec.get("filename") or rec.get("id", "")
        path = find_image(filename)
        if not path:
            print(f"  [SKIP] {filename} — file not found on disk")
            skipped += 1
            continue

        details = extract_c2pa_details_from_c2patool(path)
        if details is None:
            print(f"  [SKIP] {filename} — c2patool returned no data")
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
