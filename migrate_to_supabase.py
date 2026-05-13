"""
One-time migration: upload records.json to Supabase.

Usage:
    python migrate_to_supabase.py

Requires SUPABASE_URL and SUPABASE_KEY to be set in .env.
"""

import json
import pathlib
import sys

from dotenv import load_dotenv
import os

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit("Error: SUPABASE_URL and SUPABASE_KEY must be set in .env")

from supabase import create_client

client = create_client(SUPABASE_URL, SUPABASE_KEY)

DATA_FILE = pathlib.Path(__file__).parent / "records.json"
if not DATA_FILE.exists():
    sys.exit("Error: records.json not found")

records = json.loads(DATA_FILE.read_text(encoding="utf-8"))
if not records:
    sys.exit("records.json is empty — nothing to migrate")

rows = [{"id": r["id"], "data": r} for r in records if "id" in r]
skipped = len(records) - len(rows)
if skipped:
    print(f"Warning: skipped {skipped} record(s) with no 'id' field")

print(f"Uploading {len(rows)} records to Supabase...")
for i, row in enumerate(rows, 1):
    client.table("records").upsert(row).execute()
    print(f"  {i}/{len(rows)} — {row['id']}")
print("Done.")
