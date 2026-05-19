"""Unit tests for filename-computation helpers: _compute_renamed, _compute_original_renamed."""
import pathlib
import pytest
import app as flask_app
from app import _compute_renamed, _compute_original_renamed


@pytest.fixture()
def altered_root(tmp_path, monkeypatch):
    """Temp altered images/ tree with a grok/renamed/ subfolder."""
    root = tmp_path / "altered images"
    (root / "grok" / "renamed").mkdir(parents=True)
    (root / "grok" / "downloaded").mkdir(parents=True)
    monkeypatch.setattr(flask_app, "BASE", tmp_path)
    return root


@pytest.fixture()
def orig_dest(tmp_path, monkeypatch):
    """Temp 02-original-renamed/ directory."""
    dest = tmp_path / "real images" / "02-original-renamed"
    dest.mkdir(parents=True)
    monkeypatch.setattr(flask_app, "ORIG_DEST_DIR", dest)
    return dest


# ── _compute_renamed ──────────────────────────────────────────────────────────

class TestComputeRenamed:
    def test_no_existing_files_starts_at_001(self, altered_root):
        filename, exists = _compute_renamed("csafe-001.jpg", "grok-abc.png", "grok")
        assert filename == "csafe-001-b001.png"
        assert exists is False

    def test_increments_past_existing(self, altered_root):
        (altered_root / "grok" / "renamed" / "csafe-001-b001.png").touch()
        filename, exists = _compute_renamed("csafe-001.jpg", "grok-abc.png", "grok")
        assert filename == "csafe-001-b002.png"

    def test_global_max_across_models(self, tmp_path, monkeypatch):
        root = tmp_path / "altered images"
        (root / "grok" / "renamed").mkdir(parents=True)
        (root / "gemini" / "renamed").mkdir(parents=True)
        (root / "grok" / "renamed" / "csafe-001-b001.png").touch()
        (root / "gemini" / "renamed" / "csafe-001-b002.jpg").touch()
        monkeypatch.setattr(flask_app, "BASE", tmp_path)
        filename, _ = _compute_renamed("csafe-001.jpg", "grok-abc.png", "grok")
        assert filename == "csafe-001-b003.png"

    def test_already_exists_flag(self, altered_root):
        (altered_root / "grok" / "renamed" / "csafe-001-b001.png").touch()
        # b001 exists, so next computed is b002; b002 does not exist
        filename, exists = _compute_renamed("csafe-001.jpg", "grok-abc.png", "grok")
        assert filename == "csafe-001-b002.png"
        assert exists is False

    def test_already_exists_true_when_computed_dest_exists(self, altered_root):
        # Manually place the file that would be computed as b001
        (altered_root / "grok" / "renamed" / "csafe-001-b001.png").touch()
        (altered_root / "grok" / "renamed" / "csafe-001-b002.png").touch()
        filename, exists = _compute_renamed("csafe-001.jpg", "grok-abc.png", "grok")
        assert filename == "csafe-001-b003.png"
        assert exists is False

    def test_preserves_ai_file_extension(self, altered_root):
        filename, _ = _compute_renamed("csafe-001.jpg", "output.webp", "grok")
        assert filename.endswith(".webp")

    def test_stem_without_extension(self, altered_root):
        filename, _ = _compute_renamed("csafe-001", "output.png", "grok")
        assert filename == "csafe-001-b001.png"


# ── _compute_original_renamed ─────────────────────────────────────────────────

class TestComputeOriginalRenamed:
    def test_basic_rename(self, orig_dest):
        filename, exists = _compute_original_renamed("IMG_001.jpg", "csafe-001")
        assert filename == "csafe-001.jpg"
        assert exists is False

    def test_already_exists(self, orig_dest):
        (orig_dest / "csafe-001.jpg").touch()
        filename, exists = _compute_original_renamed("IMG_001.jpg", "csafe-001")
        assert filename == "csafe-001.jpg"
        assert exists is True

    def test_preserves_extension(self, orig_dest):
        filename, _ = _compute_original_renamed("photo.png", "csafe-002")
        assert filename == "csafe-002.png"

    def test_no_extension_in_original(self, orig_dest):
        filename, _ = _compute_original_renamed("photofile", "csafe-003")
        assert filename == "csafe-003"
