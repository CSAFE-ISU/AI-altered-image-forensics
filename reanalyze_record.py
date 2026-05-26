"""
Rerun forensic analysis for a record and merge the results back into Supabase.

Usage:
    python3 reanalyze_record.py <record_id> <altered_filename>

Example:
    python3 reanalyze_record.py rec_1775842271027 csafe-001-recomp-b007.jpg
"""

import json
import sys
import urllib.request
import urllib.error

BASE_URL = "http://localhost:5001"


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    record_id, filename = sys.argv[1], sys.argv[2]

    # 1. Fetch the current record
    print(f"Fetching record {record_id}...")
    records = api("GET", "/api/records")
    record = next((r for r in records if r.get("id") == record_id), None)
    if record is None:
        print(f"ERROR: record {record_id!r} not found")
        sys.exit(1)
    print(
        f"  Found: altered_filename={record.get('altered_filename')!r},"
        f" model={record.get('model')!r}"
    )

    # 2. Run the analysis pipeline via the app
    print(f"Running analysis on {filename!r}...")
    try:
        analysis = api("POST", "/api/analyze_file", {"filename": filename})
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        print(f"ERROR: analysis failed — {body.get('error', e)}")
        sys.exit(1)

    print(f"  Analysis complete. Artifacts: {analysis.get('artifacts')}")

    # 3. Merge analysis results into the record (analysis fields only)
    ANALYSIS_FIELDS = {
        "ifd0_tags",
        "indicators",
        "exif_anomalies",
        "c2pa_status",
        "c2pa_details",
        "c2pa_viewer_found",
        "c2pa_viewer_algorithm",
        "c2pa_viewer_cert_status",
        "c2pa_viewer_issued",
        "c2pa_viewer_json",
        "c2pa_viewer_notes",
        "c2pa_viewer_signed_by",
        "c2pa_viewer_software",
        "ela_source",
        "ela_mean_diff",
        "ela_std_diff",
        "ela_max_diff",
        "block_noise_std",
        "noise_skewness",
        "noise_kurtosis",
        "hf_energy_ratio",
        "artifacts",
        "artifact_notes",
    }
    for field in ANALYSIS_FIELDS:
        if field in analysis:
            record[field] = analysis[field]

    # 4. Save the updated record
    print("Saving updated record...")
    result = api("POST", f"/api/records/{record_id}", record)
    if result.get("ok"):
        print("  Saved successfully.")
    else:
        print(f"  ERROR saving: {result}")
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
