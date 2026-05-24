"""API tests for /api/analyze_file."""
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