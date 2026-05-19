"""Unit tests for pure helper functions: _format_filesize, _analyze_exif, _extract_c2pa_details."""
import pytest
from app import _format_filesize, _analyze_exif, _extract_c2pa_details


# ── _format_filesize ──────────────────────────────────────────────────────────

class TestFormatFilesize:
    def test_zero(self):
        assert _format_filesize(0) == "0 B"

    def test_bytes(self):
        assert _format_filesize(999) == "999 B"

    def test_exactly_one_kb(self):
        assert _format_filesize(1_000) == "1.0 KB"

    def test_fractional_kb(self):
        assert _format_filesize(1_500) == "1.5 KB"

    def test_exactly_one_mb(self):
        assert _format_filesize(1_000_000) == "1.0 MB"

    def test_fractional_mb(self):
        assert _format_filesize(2_500_000) == "2.5 MB"

    def test_just_below_kb(self):
        assert _format_filesize(999) == "999 B"

    def test_just_below_mb(self):
        assert _format_filesize(999_999) == "1000.0 KB"


# ── _analyze_exif ─────────────────────────────────────────────────────────────

FULL_CAMERA_TAGS = {
    "EXIF:Make": "Canon",
    "EXIF:Model": "EOS R5",
    "EXIF:DateTimeOriginal": "2024:01:15 10:30:00",
    "GPS:GPSLatitude": "41.8781",
}


class TestAnalyzeExif:
    def test_empty_dict_flags_all_missing(self):
        result = _analyze_exif({})
        assert "Camera Make absent" in result
        assert "Camera Model absent" in result
        assert "DateTimeOriginal absent" in result
        assert "GPS data absent" in result

    def test_full_camera_tags_no_anomalies(self):
        result = _analyze_exif(FULL_CAMERA_TAGS)
        assert result == "No anomalies detected."

    def test_detects_dall_e(self):
        tags = dict(FULL_CAMERA_TAGS)
        tags["XMP:Creator"] = "DALL-E 3"
        result = _analyze_exif(tags)
        assert "AI software tag" in result

    def test_detects_adobe_firefly(self):
        tags = dict(FULL_CAMERA_TAGS)
        tags["XMP:Software"] = "Adobe Firefly"
        result = _analyze_exif(tags)
        assert "AI software tag" in result

    def test_detects_midjourney(self):
        tags = dict(FULL_CAMERA_TAGS)
        tags["XMP:Rights"] = "created by Midjourney"
        result = _analyze_exif(tags)
        assert "AI software tag" in result

    def test_skips_directory_key(self):
        tags = dict(FULL_CAMERA_TAGS)
        tags["File:Directory"] = "/path/to/dall-e/images"
        result = _analyze_exif(tags)
        assert "AI software tag" not in result

    def test_skips_filename_key(self):
        tags = dict(FULL_CAMERA_TAGS)
        tags["File:FileName"] = "dall-e-output.jpg"
        result = _analyze_exif(tags)
        assert "AI software tag" not in result

    def test_missing_gps_flagged(self):
        tags = {
            "EXIF:Make": "Canon",
            "EXIF:Model": "EOS R5",
            "EXIF:DateTimeOriginal": "2024:01:15 10:30:00",
        }
        result = _analyze_exif(tags)
        assert "GPS data absent" in result

    def test_missing_make_flagged(self):
        tags = {
            "EXIF:Model": "EOS R5",
            "EXIF:DateTimeOriginal": "2024:01:15 10:30:00",
            "GPS:GPSLatitude": "41.8781",
        }
        result = _analyze_exif(tags)
        assert "Camera Make absent" in result


# ── _extract_c2pa_details ─────────────────────────────────────────────────────

JUMBF_TAGS = {
    "JUMBF:JUMDLabel": "c2pa",
    "CBOR:Claim_Generator_InfoName": "Adobe Firefly",
    "CBOR:ActionsSoftwareAgentName": "Adobe Photoshop",
    "CBOR:Claim_Generator_InfoOrgContentauthC2Pa_Rs": "1.3",
    "CBOR:ActionsAction": "c2pa.edited",
    "CBOR:ActionsDigitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia/",
    "CBOR:ValidationResultsActiveManifestFailureCode": None,
    "CBOR:ValidationResultsActiveManifestFailureExplanation": None,
}


class TestExtractC2paDetails:
    def test_no_jumbf_returns_none(self):
        result = _extract_c2pa_details({"EXIF:Make": "Canon"})
        assert result is None

    def test_jumbf_without_c2pa_returns_none(self):
        result = _extract_c2pa_details({"JUMBF:JUMDLabel": "something_else"})
        assert result is None

    def test_returns_dict_with_expected_keys(self):
        result = _extract_c2pa_details(JUMBF_TAGS)
        assert isinstance(result, dict)
        assert result["claim_generator"] == "Adobe Firefly"
        assert result["software_agent"] == "Adobe Photoshop"
        assert result["c2pa_version"] == "1.3"

    def test_actions_string_wrapped_and_stripped(self):
        result = _extract_c2pa_details(JUMBF_TAGS)
        assert result["actions"] == ["edited"]

    def test_actions_list_stripped(self):
        tags = dict(JUMBF_TAGS)
        tags["CBOR:ActionsAction"] = ["c2pa.edited", "c2pa.color_adjustments"]
        result = _extract_c2pa_details(tags)
        assert result["actions"] == ["edited", "color_adjustments"]

    def test_digital_source_type_last_segment(self):
        result = _extract_c2pa_details(JUMBF_TAGS)
        assert result["digital_source_type"] == "trainedAlgorithmicMedia"

    def test_digital_source_type_as_list(self):
        tags = dict(JUMBF_TAGS)
        tags["CBOR:ActionsDigitalSourceType"] = [
            "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture/"
        ]
        result = _extract_c2pa_details(tags)
        assert result["digital_source_type"] == "digitalCapture"

    def test_validation_failures_present(self):
        tags = dict(JUMBF_TAGS)
        tags["CBOR:ValidationResultsActiveManifestFailureCode"] = ["assertion.dataHash.mismatch"]
        tags["CBOR:ValidationResultsActiveManifestFailureExplanation"] = ["Hash mismatch"]
        result = _extract_c2pa_details(tags)
        assert result["validation_failures"] == ["assertion.dataHash.mismatch"]
        assert result["validation_failure_explanations"] == ["Hash mismatch"]

    def test_no_validation_failures_is_none(self):
        result = _extract_c2pa_details(JUMBF_TAGS)
        assert result["validation_failures"] is None

    def test_manifest_id_extracted(self):
        tags = dict(JUMBF_TAGS)
        tags["CBOR:ManifestLabel"] = "urn:c2pa:abcdef-1234"
        result = _extract_c2pa_details(tags)
        assert result["manifest_id"] == "urn:c2pa:abcdef-1234"
