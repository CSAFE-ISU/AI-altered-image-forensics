import pathlib
import pytest
from PIL import Image

import app as flask_app


@pytest.fixture()
def tmp_base(tmp_path):
    """Filesystem tree that mirrors the real repo layout."""
    (tmp_path / "real images" / "01-original").mkdir(parents=True)
    (tmp_path / "real images" / "02-original-renamed").mkdir(parents=True)
    (tmp_path / "real images" / "03-modified").mkdir(parents=True)
    (tmp_path / "altered images").mkdir(parents=True)
    (tmp_path / "analyzed images").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def app(tmp_base, monkeypatch):
    monkeypatch.setattr(flask_app, "_supabase", None)
    monkeypatch.setattr(flask_app, "BASE", tmp_base)
    monkeypatch.setattr(flask_app, "DATA_FILE", tmp_base / "records.json")
    monkeypatch.setattr(flask_app, "IMAGE_ROOTS", [
        tmp_base / "real images",
        tmp_base / "altered images",
        tmp_base / "analyzed images",
    ])
    monkeypatch.setattr(flask_app, "UPLOAD_DIR", tmp_base / "analyzed images")
    monkeypatch.setattr(flask_app, "ORIG_SRC_DIR",  tmp_base / "real images" / "01-original")
    monkeypatch.setattr(flask_app, "ORIG_DEST_DIR", tmp_base / "real images" / "02-original-renamed")
    monkeypatch.setattr(flask_app, "MOD_DIR",       tmp_base / "real images" / "03-modified")
    flask_app.app.config["TESTING"] = True
    return flask_app.app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def sample_jpeg(tmp_path):
    """8×8 RGB JPEG."""
    img = Image.new("RGB", (8, 8), color=(100, 150, 200))
    p = tmp_path / "sample.jpg"
    img.save(p, format="JPEG", quality=95)
    return p


@pytest.fixture()
def sample_png(tmp_path):
    """8×8 RGB PNG."""
    img = Image.new("RGB", (8, 8), color=(200, 100, 50))
    p = tmp_path / "sample.png"
    img.save(p, format="PNG")
    return p
