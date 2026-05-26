"""Tests for the index route and Supabase code paths."""

import pytest
from unittest.mock import MagicMock
import app as flask_app

# ── GET / ─────────────────────────────────────────────────────────────────────


class TestIndex:
    def test_tracker_html_served(self, client, tmp_base):
        (tmp_base / "tracker.html").write_text("<html>tracker</html>", encoding="utf-8")
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"tracker" in resp.data

    def test_missing_tracker_html_returns_404(self, client):
        resp = client.get("/")
        assert resp.status_code == 404


# ── Supabase code paths ───────────────────────────────────────────────────────


@pytest.fixture()
def supabase_mock(monkeypatch):
    """Replace _supabase with a MagicMock so Supabase code paths execute."""
    mock = MagicMock()
    monkeypatch.setattr(flask_app, "_supabase", mock)
    return mock


class TestGetRecordsSupabase:
    def test_returns_records_from_supabase(self, client, supabase_mock):
        mock_exec = supabase_mock.table.return_value.select.return_value.execute
        mock_exec.return_value.data = [{"data": {"id": "r1", "type": "p0"}}]
        resp = client.get("/api/records")
        assert resp.status_code == 200
        assert resp.get_json() == [{"id": "r1", "type": "p0"}]

    def test_strips_ela_image_b64_from_supabase_records(self, client, supabase_mock):
        mock_exec = supabase_mock.table.return_value.select.return_value.execute
        mock_exec.return_value.data = [
            {"data": {"id": "r1", "ela_image_b64": "bigbase64"}}
        ]
        resp = client.get("/api/records")
        assert "ela_image_b64" not in resp.get_json()[0]

    def test_supabase_error_returns_503(self, client, supabase_mock):
        supabase_mock.table.return_value.select.return_value.execute.side_effect = (
            RuntimeError("db down")
        )
        resp = client.get("/api/records")
        assert resp.status_code == 503


class TestSetRecordSupabase:
    def test_upserts_record_to_supabase(self, client, supabase_mock):
        resp = client.post("/api/records/r1", json={"id": "r1", "type": "p0"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        supabase_mock.table.return_value.upsert.assert_called_once()

    def test_strips_ela_image_b64_before_upsert(self, client, supabase_mock):
        client.post("/api/records/r1", json={"id": "r1", "ela_image_b64": "abc"})
        call_args = supabase_mock.table.return_value.upsert.call_args[0][0]
        assert "ela_image_b64" not in call_args["data"]

    def test_supabase_error_returns_503(self, client, supabase_mock):
        supabase_mock.table.return_value.upsert.return_value.execute.side_effect = (
            RuntimeError("fail")
        )
        resp = client.post("/api/records/r1", json={"id": "r1"})
        assert resp.status_code == 503


class TestDeleteRecordSupabase:
    def test_delete_calls_supabase(self, client, supabase_mock):
        resp = client.delete("/api/records/r1")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        supabase_mock.table.return_value.delete.assert_called()
