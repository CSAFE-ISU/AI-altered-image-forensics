"""Random Forest classifier constants and helpers
for the CSAFE AI Image Alteration Tracker."""

_RF_FEATURES = [
    "ela_mean_diff",
    "ela_std_diff",
    "ela_max_diff",
    "block_noise_std",
    "noise_skewness",
    "noise_kurtosis",
]
_RF_FEATURE_LABELS = {
    "ela_mean_diff": "ELA Mean Diff",
    "ela_std_diff": "ELA Std Diff",
    "ela_max_diff": "ELA Max Diff",
    "block_noise_std": "Block Noise Std",
    "noise_skewness": "Noise Skewness",
    "noise_kurtosis": "Noise Kurtosis",
    "ela_source_png": "ELA Source: PNG",
    "has_camera_exif": "Camera EXIF Present",
    "n_camera_exif_fields": "# Camera EXIF Fields",
    "has_photoshop_adobe": "Photoshop/Adobe Tags",
    "has_icc": "ICC Profile Tags",
    "has_grok_sig": "Grok Signature",
    "has_c2pa": "C2PA Manifest",
}
_INDICATOR_FEATURES = [
    "has_camera_exif",
    "n_camera_exif_fields",
    "has_photoshop_adobe",
    "has_icc",
    "has_grok_sig",
    "has_c2pa",
]


def _extract_indicator_vals(rec: dict) -> list | None:
    """Return indicator feature values for one record, or None if unavailable."""
    ind = rec.get("indicators")
    if ind is None:
        return None
    present = (ind.get("camera_exif") or {}).get("present") or {}
    return [
        1 if present else 0,
        len(present),
        1 if ind.get("photoshop_adobe") else 0,
        1 if ind.get("icc_meas_view") else 0,
        1 if ind.get("grok_signatures") else 0,
        1 if ind.get("c2pa") else 0,
    ]
