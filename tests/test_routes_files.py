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

    def test_no_altered_dir_returns_empty_when_dir_missing(self, client, monkeypatch, tmp_path):
        empty = tmp_path / "empty_base"
        empty.mkdir()
        monkeypatch.setattr(flask_app, "BASE", empty)
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

    def test_missing_dirs_returns_empty_lists(self, client, monkeypatch, tmp_path):
        empty = tmp_path / "empty_base"
        empty.mkdir()
        monkeypatch.setattr(flask_app, "BASE", empty)
        resp = client.get("/api/input_images")
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


# ── /api/copy_rename_image ────────────────────────────────────────────────────

class TestCopyRenameImage:
    def test_missing_params_returns_400(self, client):
        resp = client.post("/api/copy_rename_image", json={"model": "grok"})
        assert resp.status_code == 400

    def test_model_not_found_returns_404(self, client):
        resp = client.post(
            "/api/copy_rename_image",
            json={"input_image": "csafe-001.jpg", "ai_filename": "out.png", "model": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_source_not_found_returns_404(self, client, tmp_base):
        (tmp_base / "altered images" / "grok" / "downloaded").mkdir(parents=True)
        (tmp_base / "altered images" / "grok" / "renamed").mkdir(parents=True)
        resp = client.post(
            "/api/copy_rename_image",
            json={"input_image": "csafe-001.jpg", "ai_filename": "missing.png", "model": "grok"},
        )
        assert resp.status_code == 404

    def test_valid_copy_creates_renamed_file(self, client, tmp_base):
        downloaded = tmp_base / "altered images" / "grok" / "downloaded"
        downloaded.mkdir(parents=True)
        (tmp_base / "altered images" / "grok" / "renamed").mkdir(parents=True)
        (downloaded / "out.png").write_bytes(b"fake png")
        resp = client.post(
            "/api/copy_rename_image",
            json={"input_image": "csafe-001.jpg", "ai_filename": "out.png", "model": "grok"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        renamed_dir = tmp_base / "altered images" / "grok" / "renamed"
        assert (renamed_dir / body["filename"]).is_file()
        assert (downloaded / "out.png").is_file()  # original still in downloaded

    def test_sequence_increments_past_existing(self, client, tmp_base):
        downloaded = tmp_base / "altered images" / "grok" / "downloaded"
        renamed = tmp_base / "altered images" / "grok" / "renamed"
        downloaded.mkdir(parents=True)
        renamed.mkdir(parents=True)
        (downloaded / "out.png").write_bytes(b"fake png")
        (renamed / "csafe-001-b001.png").write_bytes(b"existing")
        resp = client.post(
            "/api/copy_rename_image",
            json={"input_image": "csafe-001.jpg", "ai_filename": "out.png", "model": "grok"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        # b001 already existed, so the new file should be b002
        assert body["filename"] == "csafe-001-b002.png"
        assert (renamed / "csafe-001-b002.png").is_file()

    def test_filename_follows_naming_convention(self, client, tmp_base):
        downloaded = tmp_base / "altered images" / "grok" / "downloaded"
        downloaded.mkdir(parents=True)
        (tmp_base / "altered images" / "grok" / "renamed").mkdir(parents=True)
        (downloaded / "output.webp").write_bytes(b"fake webp")
        resp = client.post(
            "/api/copy_rename_image",
            json={"input_image": "csafe-002.jpg", "ai_filename": "output.webp", "model": "grok"},
        )
        assert resp.status_code == 200
        filename = resp.get_json()["filename"]
        assert filename.startswith("csafe-002-b")
        assert filename.endswith(".webp")

    def test_already_exists_returns_warning(self, client, mocker):
        mocker.patch("app._compute_renamed", return_value=("csafe-001-b001.png", True))
        resp = client.post(
            "/api/copy_rename_image",
            json={"input_image": "csafe-001.jpg", "ai_filename": "out.png", "model": "grok"},
        )
        body = resp.get_json()
        assert body["ok"] is False
        assert "warning" in body
        assert body["filename"] == "csafe-001-b001.png"

    def test_no_altered_dir_returns_404(self, client, monkeypatch, tmp_path):
        empty = tmp_path / "empty_base"
        empty.mkdir()
        monkeypatch.setattr(flask_app, "BASE", empty)
        resp = client.post(
            "/api/copy_rename_image",
            json={"input_image": "csafe-001.jpg", "ai_filename": "out.png", "model": "grok"},
        )
        assert resp.status_code == 404


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

    def test_invalid_filename_returns_400(self, client):
        data = {"file": (io.BytesIO(b"data"), "")}
        resp = client.post(
            "/api/upload_original", data=data, content_type="multipart/form-data"
        )
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

    def test_invalid_filename_returns_400(self, client):
        data = {"file": (io.BytesIO(b"data"), ""), "dest_filename": ""}
        resp = client.post(
            "/api/upload_modified", data=data, content_type="multipart/form-data"
        )
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
    def test_no_file_returns_400(self, client):
        resp = client.post("/api/upload_downloaded")
        assert resp.status_code == 400

    def test_invalid_filename_returns_400(self, client, mocker):
        mocker.patch("app.secure_filename", return_value="")
        data = {
            "file": (io.BytesIO(b"data"), "output.png"),
            "model": "grok",
        }
        resp = client.post(
            "/api/upload_downloaded", data=data, content_type="multipart/form-data"
        )
        assert resp.status_code == 400

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

