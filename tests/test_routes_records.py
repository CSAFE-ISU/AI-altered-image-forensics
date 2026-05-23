"""API tests for GET/POST/DELETE /api/records*."""
import json
import pytest
import app as flask_app


class TestGetRecords:
    def test_empty_no_file_returns_empty_list(self, client):
        resp = client.get("/api/records")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_with_data_returns_list(self, client, tmp_base):
        data = [{"id": "r1", "type": "p0"}]
        (tmp_base / "records.json").write_text(json.dumps(data), encoding="utf-8")
        resp = client.get("/api/records")
        assert resp.status_code == 200
        assert resp.get_json() == data

    def test_returns_ela_image_b64_from_local_file(self, client, tmp_base):
        # Local JSON fallback returns records verbatim (stripping only happens in Supabase path).
        data = [{"id": "r1", "ela_image_b64": "somebase64data"}]
        (tmp_base / "records.json").write_text(json.dumps(data), encoding="utf-8")
        resp = client.get("/api/records")
        result = resp.get_json()
        assert result[0]["ela_image_b64"] == "somebase64data"


class TestSetRecordSingle:
    def test_upsert_creates_record(self, client, tmp_base):
        resp = client.post(
            "/api/records/r1",
            json={"id": "r1", "type": "p0"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["id"] == "r1"
        saved = json.loads((tmp_base / "records.json").read_text())
        assert any(r["id"] == "r1" for r in saved)

    def test_upsert_preserves_ela_image_b64_in_local_file(self, client, tmp_base):
        # Local JSON fallback stores records verbatim (stripping only happens in Supabase path).
        client.post(
            "/api/records/r1",
            json={"id": "r1", "ela_image_b64": "abc"},
            content_type="application/json",
        )
        saved = json.loads((tmp_base / "records.json").read_text())
        assert saved[0]["ela_image_b64"] == "abc"

    def test_non_object_body_returns_400(self, client):
        resp = client.post(
            "/api/records/r1",
            data='"not an object"',
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_upsert_replaces_existing(self, client, tmp_base):
        (tmp_base / "records.json").write_text(
            json.dumps([{"id": "r1", "type": "p0", "rating": 1}]), encoding="utf-8"
        )
        client.post("/api/records/r1", json={"id": "r1", "rating": 2})
        saved = json.loads((tmp_base / "records.json").read_text())
        r1 = next(r for r in saved if r["id"] == "r1")
        assert r1["rating"] == 2
        assert len([r for r in saved if r["id"] == "r1"]) == 1


class TestDeleteRecord:
    def test_delete_removes_record(self, client, tmp_base):
        (tmp_base / "records.json").write_text(
            json.dumps([{"id": "r1"}, {"id": "r2"}]), encoding="utf-8"
        )
        resp = client.delete("/api/records/r1")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        saved = json.loads((tmp_base / "records.json").read_text())
        assert not any(r["id"] == "r1" for r in saved)
        assert any(r["id"] == "r2" for r in saved)

    def test_delete_nonexistent_still_ok(self, client):
        resp = client.delete("/api/records/doesnotexist")
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


