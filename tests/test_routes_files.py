"""API tests for file management endpoints."""
import io
import pytest
import app as flask_app


# ── /api/models ───────────────────────────────────────────────────────────────

class TestGetModels:
    def test_no_altered_dir_returns_empty(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_sorted_model_names(self, client, tmp_base):
        (tmp_base / "altered images" / "grok").mkdir(parents=True)
        (tmp_base / "altered images" / "gemini").mkdir(parents=True)
        resp = client.get("/api/models")
        assert resp.get_json() == ["gemini", "grok"]

    def test_hidden_dirs_excluded(self, client, tmp_base):
        (tmp_base / "altered images" / ".DS_Store").mkdir(parents=True)
        (tmp_base / "altered images" / "grok").mkdir(parents=True)
        resp = client.get("/api/models")
        assert resp.get_json() == ["grok"]


# ── /api/input_images ─────────────────────────────────────────────────────────

class TestGetInputImages:
    def test_empty_dirs_returns_empty_lists(self, client):
        resp = client.get("/api/input_images")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["original"] == []
        assert body["modified"] == []

    def test_lists_files(self, client, tmp_base):
        orig = tmp_base / "real images" / "02-original-renamed"
        mod  = tmp_base / "real images" / "03-modified"
        (orig / "csafe-001.jpg").touch()
        (mod  / "csafe-001-mod.jpg").touch()
        resp = client.get("/api/input_images")
        body = resp.get_json()
        assert "csafe-001.jpg" in body["original"]
        assert "csafe-001-mod.jpg" in body["modified"]


# ── /api/compute_renamed ──────────────────────────────────────────────────────

class TestComputeRenamed:
    def test_missing_params_returns_400(self, client):
        resp = client.get("/api/compute_renamed?input_image=csafe-001.jpg")
        assert resp.status_code == 400

    def test_valid_params_returns_filename(self, client, tmp_base):
        (tmp_base / "altered images" / "grok" / "renamed").mkdir(parents=True)
        resp = client.get(
            "/api/compute_renamed?input_image=csafe-001.jpg&ai_filename=out.png&model=grok"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "filename" in body
        assert body["already_exists"] is False


# ── /api/compute_original_renamed ─────────────────────────────────────────────

class TestComputeOriginalRenamed:
    def test_missing_params_returns_400(self, client):
        resp = client.get("/api/compute_original_renamed?original_filename=IMG.jpg")
        assert resp.status_code == 400

    def test_valid_params_returns_filename(self, client):
        resp = client.get(
            "/api/compute_original_renamed?original_filename=IMG_001.jpg&study_id=csafe-001"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["filename"] == "csafe-001.jpg"


# ── /api/copy_rename_original ─────────────────────────────────────────────────

class TestCopyRenameOriginal:
    def test_missing_params_returns_400(self, client):
        resp = client.post("/api/copy_rename_original", json={"original_filename": "IMG.jpg"})
        assert resp.status_code == 400

    def test_source_not_found_returns_404(self, client):
        resp = client.post(
            "/api/copy_rename_original",
            json={"original_filename": "missing.jpg", "study_id": "csafe-001"},
        )
        assert resp.status_code == 404

    def test_valid_copy_creates_renamed_file(self, client, tmp_base):
        src = tmp_base / "real images" / "01-original" / "IMG_001.jpg"
        src.write_bytes(b"fake jpeg")
        resp = client.post(
            "/api/copy_rename_original",
            json={"original_filename": "IMG_001.jpg", "study_id": "csafe-001"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["filename"] == "csafe-001.jpg"
        assert (tmp_base / "real images" / "02-original-renamed" / "csafe-001.jpg").is_file()
        assert src.is_file()  # original still present (copy, not move)

    def test_dest_already_exists_returns_warning(self, client, tmp_base):
        (tmp_base / "real images" / "01-original" / "IMG_001.jpg").write_bytes(b"fake jpeg")
        (tmp_base / "real images" / "02-original-renamed" / "csafe-001.jpg").write_bytes(b"existing")
        resp = client.post(
            "/api/copy_rename_original",
            json={"original_filename": "IMG_001.jpg", "study_id": "csafe-001"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is False
        assert "warning" in body
        assert body["filename"] == "csafe-001.jpg"

    def test_preserves_extension(self, client, tmp_base):
        (tmp_base / "real images" / "01-original" / "photo.png").write_bytes(b"fake png")
        resp = client.post(
            "/api/copy_rename_original",
            json={"original_filename": "photo.png", "study_id": "csafe-002"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["filename"] == "csafe-002.png"


# ── /api/upload_original ──────────────────────────────────────────────────────

class TestUploadOriginal:
    def test_no_file_returns_400(self, client):
        resp = client.post("/api/upload_original")
        assert resp.status_code == 400

    def test_valid_upload_saves_file(self, client, tmp_base):
        data = {"file": (io.BytesIO(b"fake image data"), "photo.jpg")}
        resp = client.post(
            "/api/upload_original", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert (tmp_base / "real images" / "01-original" / body["filename"]).is_file()


# ── /api/upload_modified ─────────────────────────────────────────────────────

class TestUploadModified:
    def test_no_file_returns_400(self, client):
        resp = client.post("/api/upload_modified")
        assert resp.status_code == 400

    def test_valid_upload_saves_file(self, client, tmp_base):
        data = {
            "file": (io.BytesIO(b"modified image"), "mod.jpg"),
            "dest_filename": "csafe-001-mod.jpg",
        }
        resp = client.post(
            "/api/upload_modified", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        assert (tmp_base / "real images" / "03-modified" / "csafe-001-mod.jpg").is_file()

    def test_duplicate_returns_warning(self, client, tmp_base):
        (tmp_base / "real images" / "03-modified" / "csafe-001-mod.jpg").touch()
        data = {
            "file": (io.BytesIO(b"modified image"), "mod.jpg"),
            "dest_filename": "csafe-001-mod.jpg",
        }
        resp = client.post(
            "/api/upload_modified", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is False
        assert "warning" in body


# ── /api/upload_downloaded ───────────────────────────────────────────────────

class TestUploadDownloaded:
    def test_no_model_returns_400(self, client):
        data = {"file": (io.BytesIO(b"ai output"), "output.png")}
        resp = client.post(
            "/api/upload_downloaded", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 400

    def test_valid_upload_saves_file(self, client, tmp_base):
        (tmp_base / "altered images" / "grok" / "downloaded").mkdir(parents=True)
        data = {
            "file": (io.BytesIO(b"ai output"), "output.png"),
            "model": "grok",
        }
        resp = client.post(
            "/api/upload_downloaded", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


# ── /api/rename_modified ──────────────────────────────────────────────────────

class TestRenameModified:
    def test_missing_params_returns_400(self, client):
        resp = client.post("/api/rename_modified", json={"current_filename": "a.jpg"})
        assert resp.status_code == 400

    def test_source_not_found_returns_404(self, client):
        resp = client.post(
            "/api/rename_modified",
            json={"current_filename": "missing.jpg", "new_filename": "new.jpg"},
        )
        assert resp.status_code == 404

    def test_valid_rename_moves_file(self, client, tmp_base):
        src = tmp_base / "real images" / "03-modified" / "old.jpg"
        src.touch()
        resp = client.post(
            "/api/rename_modified",
            json={"current_filename": "old.jpg", "new_filename": "new.jpg"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["filename"] == "new.jpg"
        assert not src.exists()
        assert (tmp_base / "real images" / "03-modified" / "new.jpg").is_file()

    def test_dest_already_exists_returns_warning(self, client, tmp_base):
        (tmp_base / "real images" / "03-modified" / "old.jpg").touch()
        (tmp_base / "real images" / "03-modified" / "new.jpg").touch()
        resp = client.post(
            "/api/rename_modified",
            json={"current_filename": "old.jpg", "new_filename": "new.jpg"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is False
        assert "warning" in body
