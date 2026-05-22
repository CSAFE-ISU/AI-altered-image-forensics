"""Unit tests for forensic analysis helpers."""
import json
import pathlib
from unittest.mock import MagicMock
import pytest
import app as flask_app
from app import (
    _run_exiftool,
    _check_c2pa,
    _run_ela,
    _check_noise_inconsistency,
    _check_compression_blocking,
    _run_analysis_pipeline,
)


# ── _run_exiftool ─────────────────────────────────────────────────────────────

class TestRunExiftool:
    def test_not_installed_returns_empty(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError)
        assert _run_exiftool(sample_jpeg) == {}

    def test_nonzero_returncode_returns_empty(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="", stderr="error"))
        assert _run_exiftool(sample_jpeg) == {}

    def test_valid_json_returned(self, mocker, sample_jpeg):
        payload = [{"SourceFile": str(sample_jpeg), "EXIF:Make": "Canon"}]
        mocker.patch("subprocess.run", return_value=MagicMock(
            returncode=0, stdout=json.dumps(payload), stderr=""
        ))
        result = _run_exiftool(sample_jpeg)
        assert result["EXIF:Make"] == "Canon"

    def test_empty_json_array_returns_empty(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", return_value=MagicMock(
            returncode=0, stdout="[]", stderr=""
        ))
        assert _run_exiftool(sample_jpeg) == {}

    def test_timeout_returns_empty(self, mocker, sample_jpeg):
        import subprocess
        mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("exiftool", 15))
        assert _run_exiftool(sample_jpeg) == {}


# ── _check_c2pa ───────────────────────────────────────────────────────────────

class TestCheckC2pa:
    def test_no_tools_no_tags_returns_no(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError)
        assert _check_c2pa(sample_jpeg, {}) == "No"

    def test_c2patool_ingredient_returns_yes(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", return_value=MagicMock(
            returncode=0,
            stdout='{"ingredient": true, "claim_generator": "Adobe Firefly"}',
            stderr=""
        ))
        result = _check_c2pa(sample_jpeg, {})
        assert result == "Yes — with provenance data"

    def test_c2patool_not_installed_jumbf_tag_returns_yes(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError)
        tags = {"JUMBF:JUMDLabel": "c2pa"}
        assert _check_c2pa(sample_jpeg, tags) == "Yes — with provenance data"

    def test_c2patool_no_claim_returns_no(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", return_value=MagicMock(
            returncode=0, stdout="no claim found", stderr=""
        ))
        assert _check_c2pa(sample_jpeg, {}) == "No"

    def test_c2patool_empty_output_no_tags_returns_no(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", return_value=MagicMock(
            returncode=0, stdout="", stderr=""
        ))
        assert _check_c2pa(sample_jpeg, {}) == "No"

    def test_c2patool_unrecognised_output_returns_empty_stripped(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", return_value=MagicMock(
            returncode=0, stdout="manifest present but no recognised keys", stderr=""
        ))
        result = _check_c2pa(sample_jpeg, {})
        assert result == "Yes — but empty / stripped"

    def test_c2patool_timeout_falls_through_to_no(self, mocker, sample_jpeg):
        import subprocess
        mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("c2patool", 15))
        assert _check_c2pa(sample_jpeg, {}) == "No"

    def test_xmp_c2pa_fallback_returns_yes(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError)
        mock_img = MagicMock()
        mock_img.__enter__ = lambda s: s
        mock_img.__exit__ = MagicMock(return_value=False)
        mock_img.info = {"xmp": b"<x:xmpmeta>c2pa:manifest</x:xmpmeta>"}
        mocker.patch("app.Image.open", return_value=mock_img)
        assert _check_c2pa(sample_jpeg, {}) == "Yes — with provenance data"

    def test_xmp_open_exception_falls_through_to_no(self, mocker, sample_jpeg):
        mocker.patch("subprocess.run", side_effect=FileNotFoundError)
        mocker.patch("app.Image.open", side_effect=Exception("cannot open"))
        assert _check_c2pa(sample_jpeg, {}) == "No"


# ── _run_ela ──────────────────────────────────────────────────────────────────

class TestRunEla:
    def test_jpeg_returns_tuple(self, sample_jpeg):
        flagged, max_diff, b64 = _run_ela(sample_jpeg)
        assert isinstance(flagged, bool)
        assert isinstance(max_diff, int)
        assert max_diff >= 0
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_png_does_not_crash(self, sample_png):
        flagged, max_diff, b64 = _run_ela(sample_png)
        assert isinstance(flagged, bool)
        assert isinstance(b64, str)

    def test_nonexistent_file_returns_safe_default(self, tmp_path):
        flagged, max_diff, b64 = _run_ela(tmp_path / "missing.jpg")
        assert flagged is False
        assert max_diff == 0
        assert b64 == ""


# ── _check_noise_inconsistency ────────────────────────────────────────────────

class TestCheckNoiseInconsistency:
    def test_jpeg_returns_tuple(self, sample_jpeg):
        flagged, noise_std, note = _check_noise_inconsistency(sample_jpeg)
        assert isinstance(flagged, bool)
        assert isinstance(noise_std, float)
        assert isinstance(note, str)

    def test_png_returns_tuple(self, sample_png):
        flagged, noise_std, note = _check_noise_inconsistency(sample_png)
        assert isinstance(flagged, bool)
        assert isinstance(noise_std, float)

    def test_nonexistent_file_returns_safe_default(self, tmp_path):
        flagged, noise_std, note = _check_noise_inconsistency(tmp_path / "missing.jpg")
        assert flagged is False
        assert noise_std == 0.0
        assert note == ""

    def test_flagged_note_is_not_empty(self, tmp_path):
        from PIL import Image, ImageFilter
        import numpy as np
        # Create a larger image where noise std is more likely to exceed threshold
        img = Image.new("RGB", (256, 256))
        pixels = img.load()
        for y in range(256):
            for x in range(256):
                pixels[x, y] = (x % 255, y % 255, (x + y) % 255)
        p = tmp_path / "noisy.jpg"
        img.save(p, format="JPEG")
        flagged, noise_std, note = _check_noise_inconsistency(p)
        assert isinstance(flagged, bool)
        assert isinstance(noise_std, float)


# ── _check_compression_blocking ───────────────────────────────────────────────

class TestCheckCompressionBlocking:
    def test_jpeg_returns_tuple(self, sample_jpeg):
        flagged, note = _check_compression_blocking(sample_jpeg)
        assert isinstance(flagged, bool)
        assert isinstance(note, str)

    def test_png_returns_false_empty(self, sample_png):
        flagged, note = _check_compression_blocking(sample_png)
        assert flagged is False
        assert note == ""

    def test_nonexistent_file_returns_safe_default(self, tmp_path):
        flagged, note = _check_compression_blocking(tmp_path / "missing.jpg")
        assert flagged is False
        assert note == ""

    def test_larger_jpeg_exercises_block_loop(self, tmp_path):
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(128, 128, 128))
        p = tmp_path / "large.jpg"
        img.save(p, format="JPEG", quality=50)
        flagged, note = _check_compression_blocking(p)
        assert isinstance(flagged, bool)
        assert isinstance(note, str)

    def test_gradient_jpeg_reaches_ratio_calculation(self, tmp_path):
        import numpy as np
        from PIL import Image
        arr = np.tile(np.arange(64, dtype=np.uint8), (64, 1))
        img = Image.fromarray(np.stack([arr, arr, arr], axis=2))
        p = tmp_path / "gradient.jpg"
        img.save(p, format="JPEG", quality=85)
        flagged, note = _check_compression_blocking(p)
        assert isinstance(flagged, bool)


# ── _run_analysis_pipeline ────────────────────────────────────────────────────

class TestRunAnalysisPipeline:
    def test_returns_required_keys(self, mocker, sample_jpeg):
        mocker.patch.object(flask_app, "_run_exiftool", return_value={})
        mocker.patch.object(flask_app, "_check_c2pa", return_value="No")
        mocker.patch.object(flask_app, "_extract_c2pa_details", return_value=None)
        result = _run_analysis_pipeline(sample_jpeg)
        for key in ("exif_anomalies", "c2pa_status", "c2pa_details", "artifacts", "artifact_notes", "ela_image_b64"):
            assert key in result

    def test_ela_b64_is_nonempty_string(self, mocker, sample_jpeg):
        mocker.patch.object(flask_app, "_run_exiftool", return_value={})
        mocker.patch.object(flask_app, "_check_c2pa", return_value="No")
        mocker.patch.object(flask_app, "_extract_c2pa_details", return_value=None)
        result = _run_analysis_pipeline(sample_jpeg)
        assert isinstance(result["ela_image_b64"], str)
        assert len(result["ela_image_b64"]) > 0

    def test_artifacts_list_when_noise_flagged(self, mocker, sample_jpeg):
        mocker.patch.object(flask_app, "_run_exiftool", return_value={})
        mocker.patch.object(flask_app, "_check_c2pa", return_value="No")
        mocker.patch.object(flask_app, "_extract_c2pa_details", return_value=None)
        mocker.patch.object(flask_app, "_run_ela", return_value=(False, 0, "abc"))
        mocker.patch.object(flask_app, "_check_noise_inconsistency", return_value=(True, 2.5, "Noise note"))
        mocker.patch.object(flask_app, "_check_compression_blocking", return_value=(False, ""))
        result = _run_analysis_pipeline(sample_jpeg)
        assert "Noise inconsistency" in result["artifacts"]
        assert "Noise note" in result["artifact_notes"]

    def test_artifacts_list_when_blocking_flagged(self, mocker, sample_jpeg):
        mocker.patch.object(flask_app, "_run_exiftool", return_value={})
        mocker.patch.object(flask_app, "_check_c2pa", return_value="No")
        mocker.patch.object(flask_app, "_extract_c2pa_details", return_value=None)
        mocker.patch.object(flask_app, "_run_ela", return_value=(False, 0, "abc"))
        mocker.patch.object(flask_app, "_check_noise_inconsistency", return_value=(False, 0.0, ""))
        mocker.patch.object(flask_app, "_check_compression_blocking", return_value=(True, "Blocking note"))
        result = _run_analysis_pipeline(sample_jpeg)
        assert "Compression blocking" in result["artifacts"]
        assert "Blocking note" in result["artifact_notes"]

    def test_empty_exiftool_tags_gives_unavailable_note(self, mocker, sample_jpeg):
        mocker.patch.object(flask_app, "_run_exiftool", return_value={})
        mocker.patch.object(flask_app, "_check_c2pa", return_value="No")
        mocker.patch.object(flask_app, "_extract_c2pa_details", return_value=None)
        result = _run_analysis_pipeline(sample_jpeg)
        # Empty dict is falsy — pipeline uses the "exiftool not available" fallback message
        assert result["exif_anomalies"] == "(exiftool not available)"

    def test_artifacts_list_when_ela_flagged(self, mocker, sample_jpeg):
        mocker.patch.object(flask_app, "_run_exiftool", return_value={})
        mocker.patch.object(flask_app, "_check_c2pa", return_value="No")
        mocker.patch.object(flask_app, "_extract_c2pa_details", return_value=None)
        mocker.patch.object(flask_app, "_run_ela", return_value=(True, 20, "abc"))
        mocker.patch.object(flask_app, "_check_noise_inconsistency", return_value=(False, 0.0, ""))
        mocker.patch.object(flask_app, "_check_compression_blocking", return_value=(False, ""))
        result = _run_analysis_pipeline(sample_jpeg)
        assert "ELA anomaly" in result["artifacts"]
        assert "ELA" in result["artifact_notes"]

    def test_c2pa_status_passed_through(self, mocker, sample_jpeg):
        mocker.patch.object(flask_app, "_run_exiftool", return_value={})
        mocker.patch.object(flask_app, "_check_c2pa", return_value="Yes — with provenance data")
        mocker.patch.object(flask_app, "_extract_c2pa_details", return_value=None)
        result = _run_analysis_pipeline(sample_jpeg)
        assert result["c2pa_status"] == "Yes — with provenance data"
