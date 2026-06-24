"""API tests for /api/aiornot."""

from PIL import Image
import app as flask_app

MOCK_RESULT = {
    "aiornot_verdict": "ai",
    "aiornot_decision": "Likely AI",
    "aiornot_prob_ai": 0.95,
    "aiornot_prob_human": 0.05,
    "aiornot_prob_deepfake": 0.0,
    "aiornot_generators": [{"label": "Flux", "confidence": 0.9}],
    "aiornot_id": "abc",
    "aiornot_created_at": "2026-01-01T00:00:00Z",
}


class TestAiOrNotRoute:
    def test_missing_key_returns_503(self, mocker, client):
        mocker.patch.object(flask_app, "_AIORNOT_API_KEY", "")
        resp = client.post("/api/aiornot", json={"filename": "x.jpg"})
        assert resp.status_code == 503

    def test_missing_filename_returns_400(self, mocker, client):
        mocker.patch.object(flask_app, "_AIORNOT_API_KEY", "secret")
        resp = client.post("/api/aiornot", json={})
        assert resp.status_code == 400

    def test_file_not_found_returns_404(self, mocker, client):
        mocker.patch.object(flask_app, "_AIORNOT_API_KEY", "secret")
        resp = client.post("/api/aiornot", json={"filename": "nosuchfile.jpg"})
        assert resp.status_code == 404

    def test_valid_file_returns_result(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_AIORNOT_API_KEY", "secret")
        mock_query = mocker.patch.object(
            flask_app, "query_aiornot", return_value=MOCK_RESULT
        )
        dest = tmp_base / "analyzed images" / "test.jpg"
        Image.new("RGB", (8, 8)).save(str(dest), format="JPEG")
        resp = client.post("/api/aiornot", json={"filename": "test.jpg"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["aiornot_decision"] == "Likely AI"
        # The API key, not the filename, is passed to the client function.
        assert mock_query.call_args.args[1] == "secret"

    def test_query_exception_returns_502(self, mocker, client, tmp_base):
        mocker.patch.object(flask_app, "_AIORNOT_API_KEY", "secret")
        mocker.patch.object(
            flask_app, "query_aiornot", side_effect=RuntimeError("boom")
        )
        dest = tmp_base / "analyzed images" / "test.jpg"
        Image.new("RGB", (8, 8)).save(str(dest), format="JPEG")
        resp = client.post("/api/aiornot", json={"filename": "test.jpg"})
        assert resp.status_code == 502
