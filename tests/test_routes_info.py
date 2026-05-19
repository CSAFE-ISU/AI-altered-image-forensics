"""API tests for info and file-discovery endpoints."""
import io
import pytest
from PIL import Image
import app as flask_app


# ── /images/<filename> ────────────────────────────────────────────────────────

class TestServeImage:
    def test_not_found_returns_404(self, client):
        resp = client.get("/images/nosuchfile.jpg")
        assert resp.status_code == 404

    def test_serves_existing_file(self, client, tmp_base):
        img = Image.new("RGB", (8, 8))
        dest = tmp_base / "analyzed images" / "serve_me.jpg"
        img.save(str(dest), format="JPEG")
        resp = client.get("/images/serve_me.jpg")
        assert resp.status_code == 200


# ── /api/original_files ───────────────────────────────────────────────────────

class TestGetOriginalFiles:
    def test_empty_dir_returns_empty_list(self, client):
        resp = client.get("/api/original_files")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_lists_files_in_01_original(self, client, tmp_base):
        (tmp_base / "real images" / "01-original" / "IMG_001.jpg").touch()
        (tmp_base / "real images" / "01-original" / "IMG_002.jpg").touch()
        resp = client.get("/api/original_files")
        body = resp.get_json()
        assert "IMG_001.jpg" in body
        assert "IMG_002.jpg" in body

    def test_hidden_files_excluded(self, client, tmp_base):
        (tmp_base / "real images" / "01-original" / ".DS_Store").touch()
        (tmp_base / "real images" / "01-original" / "IMG_001.jpg").touch()
        resp = client.get("/api/original_files")
        assert ".DS_Store" not in resp.get_json()


# ── /api/original_image_info ─────────────────────────────────────────────────

class TestOriginalImageInfo:
    def test_missing_filename_returns_400(self, client):
        resp = client.get("/api/original_image_info")
        assert resp.status_code == 400

    def test_file_not_found_returns_404(self, client):
        resp = client.get("/api/original_image_info?filename=nosuchfile.jpg")
        assert resp.status_code == 404

    def test_valid_file_returns_filesize_and_dims(self, client, tmp_base):
        img = Image.new("RGB", (100, 80))
        dest = tmp_base / "analyzed images" / "info_test.jpg"
        img.save(str(dest), format="JPEG")
        resp = client.get("/api/original_image_info?filename=info_test.jpg")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "filesize" in body
        assert "100" in body["dimensions"]
        assert "80" in body["dimensions"]

    def test_corrupt_file_returns_500(self, mocker, client, tmp_base):
        dest = tmp_base / "analyzed images" / "corrupt.jpg"
        dest.write_bytes(b"not an image")
        resp = client.get("/api/original_image_info?filename=corrupt.jpg")
        assert resp.status_code == 500


# ── /api/image_info ───────────────────────────────────────────────────────────

class TestImageInfo:
    def test_missing_params_returns_400(self, client):
        resp = client.get("/api/image_info?model=grok")
        assert resp.status_code == 400

    def test_model_not_found_returns_404(self, client):
        resp = client.get("/api/image_info?model=nonexistent&filename=out.png")
        assert resp.status_code == 404

    def test_file_not_found_returns_404(self, client, tmp_base):
        (tmp_base / "altered images" / "grok" / "downloaded").mkdir(parents=True)
        resp = client.get("/api/image_info?model=grok&filename=missing.png")
        assert resp.status_code == 404

    def test_valid_file_returns_format_and_dims(self, client, tmp_base):
        downloaded = tmp_base / "altered images" / "grok" / "downloaded"
        downloaded.mkdir(parents=True)
        img = Image.new("RGB", (64, 48))
        img.save(str(downloaded / "ai_out.png"), format="PNG")
        resp = client.get("/api/image_info?model=grok&filename=ai_out.png")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["format"] == "PNG"
        assert "64" in body["dimensions"]
        assert "48" in body["dimensions"]

    def test_corrupt_file_returns_500(self, client, tmp_base):
        downloaded = tmp_base / "altered images" / "grok" / "downloaded"
        downloaded.mkdir(parents=True)
        (downloaded / "bad.jpg").write_bytes(b"not an image")
        resp = client.get("/api/image_info?model=grok&filename=bad.jpg")
        assert resp.status_code == 500


# ── /api/downloaded_files ─────────────────────────────────────────────────────

class TestGetDownloadedFiles:
    def test_missing_model_returns_400(self, client):
        resp = client.get("/api/downloaded_files")
        assert resp.status_code == 400

    def test_model_not_found_returns_empty_list(self, client):
        resp = client.get("/api/downloaded_files?model=nonexistent")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_no_downloaded_dir_returns_empty_list(self, client, tmp_base):
        (tmp_base / "altered images" / "grok").mkdir(parents=True)
        resp = client.get("/api/downloaded_files?model=grok")
        assert resp.get_json() == []

    def test_lists_files_in_downloaded(self, client, tmp_base):
        downloaded = tmp_base / "altered images" / "grok" / "downloaded"
        downloaded.mkdir(parents=True)
        (downloaded / "img1.png").touch()
        (downloaded / "img2.jpg").touch()
        resp = client.get("/api/downloaded_files?model=grok")
        body = resp.get_json()
        assert "img1.png" in body
        assert "img2.jpg" in body

    def test_hidden_files_excluded(self, client, tmp_base):
        downloaded = tmp_base / "altered images" / "grok" / "downloaded"
        downloaded.mkdir(parents=True)
        (downloaded / ".DS_Store").touch()
        (downloaded / "img1.png").touch()
        resp = client.get("/api/downloaded_files?model=grok")
        assert ".DS_Store" not in resp.get_json()
