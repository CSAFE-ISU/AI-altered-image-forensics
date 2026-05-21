"""Unit tests for pure helper functions: _format_filesize, _analyze_exif, _extract_c2pa_details,
_detect_c2pa_from_tags, _detect_indicators."""
import pytest
from app import _format_filesize, _analyze_exif, _extract_c2pa_details, _detect_c2pa_from_tags, _detect_indicators


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

    def test_skips_skip_fields_key(self):
        tags = dict(FULL_CAMERA_TAGS)
        tags["SourceFile"] = "/path/to/dall-e/output.jpg"
        result = _analyze_exif(tags)
        assert "AI software tag" not in result

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

    def test_validation_failures_as_strings_coerced_to_list(self):
        tags = dict(JUMBF_TAGS)
        tags["CBOR:ValidationResultsActiveManifestFailureCode"] = "assertion.dataHash.mismatch"
        tags["CBOR:ValidationResultsActiveManifestFailureExplanation"] = "Hash mismatch"
        result = _extract_c2pa_details(tags)
        assert result["validation_failures"] == ["assertion.dataHash.mismatch"]
        assert result["validation_failure_explanations"] == ["Hash mismatch"]

    def test_manifest_id_extracted(self):
        tags = dict(JUMBF_TAGS)
        tags["CBOR:ManifestLabel"] = "urn:c2pa:abcdef-1234"
        result = _extract_c2pa_details(tags)
        assert result["manifest_id"] == "urn:c2pa:abcdef-1234"


# ── _detect_c2pa_from_tags ────────────────────────────────────────────────────

CBOR_TAGS = {
    "JUMBF:JUMDLabel": "c2pa",
    "CBOR:Claim_Generator_InfoName": "Black Forest Labs API",
    "CBOR:ActionsSoftwareAgent": "Flux.2",
    "CBOR:Claim_Generator_InfoOrgContentauthC2Pa_Rs": "0.67.0",
    "CBOR:ActionsAction": "c2pa.created",
    "CBOR:ActionsDigitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
    "CBOR:InstanceID": "xmp:iid:4a11d9bc-2ea9-47d8-a64a-a04f83610fad",
}


class TestDetectC2paFromTags:
    def test_no_jumbf_no_cbor_returns_none(self):
        assert _detect_c2pa_from_tags({"IFD0:Make": "Canon"}) is None

    def test_empty_dict_returns_none(self):
        assert _detect_c2pa_from_tags({}) is None

    def test_jumbf_c2pa_label_triggers_detection(self):
        result = _detect_c2pa_from_tags({"JUMBF:JUMDLabel": "c2pa"})
        assert result is not None
        assert result["status"] == "found"

    def test_cbor_key_without_jumbf_triggers_detection(self):
        result = _detect_c2pa_from_tags({"CBOR:Claim_Generator_InfoName": "Adobe"})
        assert result is not None
        assert result["status"] == "found"

    def test_claim_generator_extracted(self):
        result = _detect_c2pa_from_tags(CBOR_TAGS)
        assert result["claim_generator"] == "Black Forest Labs API"

    def test_software_agent_from_primary_key(self):
        result = _detect_c2pa_from_tags(CBOR_TAGS)
        assert result["software_agent"] == "Flux.2"

    def test_software_agent_fallback_to_name_key(self):
        tags = {**CBOR_TAGS, "CBOR:ActionsSoftwareAgentName": "GPT-4o"}
        del tags["CBOR:ActionsSoftwareAgent"]
        result = _detect_c2pa_from_tags(tags)
        assert result["software_agent"] == "GPT-4o"

    def test_c2pa_version_extracted(self):
        result = _detect_c2pa_from_tags(CBOR_TAGS)
        assert result["c2pa_version"] == "0.67.0"

    def test_actions_string_wrapped_in_list(self):
        result = _detect_c2pa_from_tags(CBOR_TAGS)
        assert result["actions"] == ["c2pa.created"]

    def test_actions_list_preserved(self):
        tags = {**CBOR_TAGS, "CBOR:ActionsAction": ["c2pa.created", "c2pa.edited"]}
        result = _detect_c2pa_from_tags(tags)
        assert result["actions"] == ["c2pa.created", "c2pa.edited"]

    def test_digital_source_type_last_segment(self):
        result = _detect_c2pa_from_tags(CBOR_TAGS)
        assert result["digital_source_type"] == "trainedAlgorithmicMedia"

    def test_digital_source_type_trailing_slash_stripped(self):
        tags = {**CBOR_TAGS, "CBOR:ActionsDigitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture/"}
        result = _detect_c2pa_from_tags(tags)
        assert result["digital_source_type"] == "digitalCapture"

    def test_digital_source_type_as_list_uses_first(self):
        tags = {**CBOR_TAGS, "CBOR:ActionsDigitalSourceType": ["http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia", "http://example.com/other"]}
        result = _detect_c2pa_from_tags(tags)
        assert result["digital_source_type"] == "trainedAlgorithmicMedia"

    def test_manifest_id_extracted(self):
        result = _detect_c2pa_from_tags(CBOR_TAGS)
        assert result["manifest_id"] == "xmp:iid:4a11d9bc-2ea9-47d8-a64a-a04f83610fad"

    def test_no_validation_failures_key_absent(self):
        result = _detect_c2pa_from_tags(CBOR_TAGS)
        assert "validation_failures" not in result

    def test_validation_failures_as_string_wrapped_in_list(self):
        tags = {**CBOR_TAGS, "CBOR:ValidationResultsActiveManifestFailureCode": "signingCredential.untrusted"}
        result = _detect_c2pa_from_tags(tags)
        assert result["validation_failures"] == ["signingCredential.untrusted"]

    def test_validation_failures_as_list_preserved(self):
        tags = {**CBOR_TAGS, "CBOR:ValidationResultsActiveManifestFailureCode": ["err.a", "err.b"]}
        result = _detect_c2pa_from_tags(tags)
        assert result["validation_failures"] == ["err.a", "err.b"]

    def test_validation_failure_explanations_included(self):
        tags = {
            **CBOR_TAGS,
            "CBOR:ValidationResultsActiveManifestFailureCode": "signingCredential.untrusted",
            "CBOR:ValidationResultsActiveManifestFailureExplanation": "signing certificate untrusted",
        }
        result = _detect_c2pa_from_tags(tags)
        assert result["validation_failure_explanations"] == ["signing certificate untrusted"]

    def test_missing_optional_fields_absent_from_result(self):
        result = _detect_c2pa_from_tags({"JUMBF:JUMDLabel": "c2pa"})
        assert "claim_generator" not in result
        assert "software_agent" not in result
        assert "c2pa_version" not in result
        assert "actions" not in result
        assert "digital_source_type" not in result
        assert "manifest_id" not in result


# ── _detect_indicators ────────────────────────────────────────────────────────

CAMERA_TAGS = {
    "IFD0:Make": "Canon",
    "IFD0:Model": "EOS R5",
    "IFD0:Software": "Digital Photo Professional",
    "ExifIFD:DateTimeOriginal": "2024:01:15 10:30:00",
    "ExifIFD:CreateDate": "2024:01:15 10:30:00",
    "ExifIFD:ISO": "400",
    "ExifIFD:FocalLength": "50.0 mm",
    "ExifIFD:ExposureTime": "1/250",
    "ExifIFD:FNumber": "2.8",
    "ExifIFD:MeteringMode": "Multi-segment",
    "ExifIFD:WhiteBalance": "Auto",
    "ExifIFD:Flash": "No flash",
    "ExifIFD:SceneType": "Directly photographed",
    "ExifIFD:LensMake": "Canon",
    "ExifIFD:LensModel": "EF 50mm f/1.4",
}


class TestDetectIndicators:
    def test_returns_required_keys(self):
        result = _detect_indicators({})
        assert "summary" in result
        assert "camera_exif" in result
        assert "photoshop_adobe" in result
        assert "icc_meas_view" in result
        assert "grok_signatures" in result
        assert "c2pa" in result

    def test_empty_tags_camera_absent(self):
        result = _detect_indicators({})
        assert "Camera EXIF: absent" in result["summary"]
        assert result["camera_exif"]["present"] == {}
        assert len(result["camera_exif"]["absent"]) == 15

    def test_full_camera_tags_present(self):
        result = _detect_indicators(CAMERA_TAGS)
        assert "Camera EXIF: present (15 fields)" in result["summary"]
        assert len(result["camera_exif"]["present"]) == 15
        assert result["camera_exif"]["absent"] == []

    def test_partial_camera_tags_count_correct(self):
        result = _detect_indicators({"IFD0:Make": "Canon", "IFD0:Model": "EOS R5"})
        assert "Camera EXIF: present (2 fields)" in result["summary"]
        assert len(result["camera_exif"]["absent"]) == 13

    def test_photoshop_tags_detected(self):
        tags = {**CAMERA_TAGS, "Photoshop:ColorMode": "3", "Photoshop:IPTCDigest": "abc"}
        result = _detect_indicators(tags)
        assert "Photoshop/Adobe markers detected" in result["summary"]
        assert result["photoshop_adobe"] is not None

    def test_adobe_tags_detected(self):
        tags = {**CAMERA_TAGS, "Adobe:DCTEncodeVersion": "1"}
        result = _detect_indicators(tags)
        assert "Photoshop/Adobe markers detected" in result["summary"]

    def test_no_photoshop_tags_returns_none(self):
        result = _detect_indicators(CAMERA_TAGS)
        assert result["photoshop_adobe"] is None
        assert "Photoshop/Adobe" not in result["summary"]

    def test_icc_meas_tags_detected(self):
        tags = {**CAMERA_TAGS, "ICC-meas:MeasurementObserver": "CIE 1931"}
        result = _detect_indicators(tags)
        assert "ICC measurement/viewing conditions detected" in result["summary"]
        assert result["icc_meas_view"] is not None

    def test_icc_view_tags_detected(self):
        tags = {**CAMERA_TAGS, "ICC-view:ViewingCondDesc": "Reference"}
        result = _detect_indicators(tags)
        assert "ICC measurement/viewing conditions detected" in result["summary"]

    def test_no_icc_tags_returns_none(self):
        result = _detect_indicators(CAMERA_TAGS)
        assert result["icc_meas_view"] is None

    def test_grok_artist_uuid_detected(self):
        tags = {**CAMERA_TAGS, "IFD0:Artist": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
        result = _detect_indicators(tags)
        assert "Grok signature detected" in result["summary"]
        assert result["grok_signatures"]["artist"] is not None

    def test_grok_user_comment_signature_detected(self):
        tags = {**CAMERA_TAGS, "ExifIFD:UserComment": "Signature: abc123"}
        result = _detect_indicators(tags)
        assert "Grok signature detected" in result["summary"]
        assert result["grok_signatures"]["user_comment"] is not None

    def test_non_uuid_artist_not_detected_as_grok(self):
        tags = {**CAMERA_TAGS, "IFD0:Artist": "Jane Smith"}
        result = _detect_indicators(tags)
        assert "Grok signature detected" not in result["summary"]
        assert result["grok_signatures"] is None

    def test_no_grok_tags_returns_none(self):
        result = _detect_indicators(CAMERA_TAGS)
        assert result["grok_signatures"] is None

    def test_c2pa_tags_detected(self):
        tags = {**CAMERA_TAGS, "JUMBF:JUMDLabel": "c2pa", "CBOR:Claim_Generator_InfoName": "Adobe"}
        result = _detect_indicators(tags)
        assert "C2PA manifest detected" in result["summary"]
        assert result["c2pa"] is not None
        assert result["c2pa"]["claim_generator"] == "Adobe"

    def test_no_c2pa_tags_returns_none(self):
        result = _detect_indicators(CAMERA_TAGS)
        assert result["c2pa"] is None
        assert "C2PA" not in result["summary"]

    def test_summary_combines_multiple_indicators(self):
        tags = {
            **CAMERA_TAGS,
            "Photoshop:ColorMode": "3",
            "ICC-meas:MeasurementObserver": "CIE 1931",
            "JUMBF:JUMDLabel": "c2pa",
        }
        result = _detect_indicators(tags)
        assert "Camera EXIF: present" in result["summary"]
        assert "Photoshop/Adobe markers detected" in result["summary"]
        assert "ICC measurement/viewing conditions detected" in result["summary"]
        assert "C2PA manifest detected" in result["summary"]
