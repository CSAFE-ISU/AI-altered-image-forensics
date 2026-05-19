"""API tests for /api/analyze, /api/analyze_file, /api/upload_and_analyze."""
import io
import pytest
from PIL import Image
import app as flask_app

MOCK_RESULT = {
    "exif_anomalies": "Camera Make absent",
    "c2pa_status": "No",
    "c2pa_details": None,
    "artifacts": [],
    "artifact_notes": "",
    "ela_image_b64": "abc123",
}


# ── /api/analyze ──────────────────────────────────────────────────────────────

class TestAnalyzeImage:
    def test_missing_params_returns_400(self, client):
        resp = client.post("/api/analyze", json={"model": "grok"})
        assert resp.status_code == 400

    def test_model_not_found_returns_404(self, client):
        resp = client.post(
            "/api/analyze",
            json={"altered_filename": "csafe-001-b001.jpg", "model": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_file_not_found_returns_404(self, client, tmp_base):
        (tmp_base / "altered images" / "grok" / "renamed").mkdir(parents=True)
        resp = client.post(
            "/api/analyze",
            json={"altered_filename": "missing.jpg", "model": "grok"},
        )
        assert resp.status_code == 404

    def test_valid_file_returns_analysis(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_run_analysis_pipeline", return_value=MOCK_RESULT)
        renamed = tmp_base / "altered images" / "grok" / "renamed"
        renamed.mkdir(parents=True)
        img = Image.new("RGB", (8, 8))
        img.save(str(renamed / "csafe-001-b001.jpg"), format="JPEG")
        resp = client.post(
            "/api/analyze",
            json={"altered_filename": "csafe-001-b001.jpg", "model": "grok"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        for key in MOCK_RESULT:
            assert key in body

    def test_pipeline_exception_returns_500(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_run_analysis_pipeline", side_effect=RuntimeError("boom"))
        renamed = tmp_base / "altered images" / "grok" / "renamed"
        renamed.mkdir(parents=True)
        Image.new("RGB", (8, 8)).save(str(renamed / "csafe-001-b001.jpg"), format="JPEG")
        resp = client.post(
            "/api/analyze",
            json={"altered_filename": "csafe-001-b001.jpg", "model": "grok"},
        )
        assert resp.status_code == 500


# ── /api/analyze_file ─────────────────────────────────────────────────────────

class TestAnalyzeFile:
    def test_missing_filename_returns_400(self, client):
        resp = client.post("/api/analyze_file", json={})
        assert resp.status_code == 400

    def test_file_not_found_returns_404(self, client):
        resp = client.post("/api/analyze_file", json={"filename": "nosuchfile.jpg"})
        assert resp.status_code == 404

    def test_valid_file_returns_analysis(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_run_analysis_pipeline", return_value=MOCK_RESULT)
        dest = tmp_base / "analyzed images" / "test.jpg"
        img = Image.new("RGB", (8, 8))
        img.save(str(dest), format="JPEG")
        resp = client.post("/api/analyze_file", json={"filename": "test.jpg"})
        assert resp.status_code == 200
        body = resp.get_json()
        for key in MOCK_RESULT:
            assert key in body

    def test_pipeline_exception_returns_500(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_run_analysis_pipeline", side_effect=RuntimeError("boom"))
        dest = tmp_base / "analyzed images" / "test.jpg"
        Image.new("RGB", (8, 8)).save(str(dest), format="JPEG")
        resp = client.post("/api/analyze_file", json={"filename": "test.jpg"})
        assert resp.status_code == 500


# ── /api/upload_and_analyze ───────────────────────────────────────────────────

class TestUploadAndAnalyze:
    def test_no_file_returns_400(self, client):
        resp = client.post("/api/upload_and_analyze")
        assert resp.status_code == 400

    def test_empty_filename_returns_400(self, client):
        data = {"file": (io.BytesIO(b"data"), "")}
        resp = client.post(
            "/api/upload_and_analyze", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 400

    def test_invalid_filename_after_sanitize_returns_400(self, mocker, client):
        mocker.patch("app.secure_filename", return_value="")
        data = {"file": (io.BytesIO(b"data"), "output.jpg")}
        resp = client.post(
            "/api/upload_and_analyze", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 400

    def test_non_image_file_returns_result_with_empty_dims(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_run_analysis_pipeline", return_value=MOCK_RESULT)
        data = {"file": (io.BytesIO(b"not an image at all"), "data.jpg")}
        resp = client.post(
            "/api/upload_and_analyze", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["dims"] == ""

    def test_valid_upload_returns_analysis(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_run_analysis_pipeline", return_value=MOCK_RESULT)
        buf = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buf, format="JPEG")
        buf.seek(0)
        data = {"file": (buf, "upload.jpg")}
        resp = client.post(
            "/api/upload_and_analyze", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "filename" in body
        assert "filesize" in body
        assert "dims" in body
        for key in MOCK_RESULT:
            assert key in body

    def test_pipeline_exception_returns_500(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_run_analysis_pipeline", side_effect=RuntimeError("boom"))
        buf = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buf, format="JPEG")
        buf.seek(0)
        data = {"file": (buf, "upload.jpg")}
        resp = client.post(
            "/api/upload_and_analyze", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 500
