"""API tests for /api/random_forest."""
import json
import sys
import numpy as np
import pytest
from unittest.mock import MagicMock
import app as flask_app


@pytest.fixture()
def supabase_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(flask_app, "_supabase", mock)
    return mock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pixel_rec(rtype, idx, model="grok", include_all_features=True):
    rec = {"id": f"rec_{idx}", "type": rtype, "ela_source": "jpeg"}
    if include_all_features:
        rec.update({
            "ela_mean_diff":   5.0 + idx * 0.1,
            "ela_std_diff":    2.0,
            "ela_max_diff":    20.0 + idx,
            "block_noise_std": 0.5,
            "noise_skewness":  0.1,
            "noise_kurtosis":  0.2,
        })
    if rtype == "p2":
        rec["model"] = model
    return rec


def _indicator_rec(rtype, idx, model="grok"):
    rec = _pixel_rec(rtype, idx, model)
    rec["indicators"] = {
        "camera_exif":    {"present": {"Make": "Canon", "Model": "EOS"}},
        "photoshop_adobe": False,
        "icc_meas_view":   False,
        "grok_signatures": False,
        "c2pa":            False,
    }
    return rec


def _make_dataset(n_orig=5, n_alt=5, model="grok"):
    originals = [_pixel_rec("p0", i) for i in range(n_orig)]
    altered   = [_pixel_rec("p2", i + n_orig, model=model) for i in range(n_alt)]
    return originals + altered


# ── sklearn mock fixture ──────────────────────────────────────────────────────

@pytest.fixture()
def sklearn_mocks(monkeypatch):
    """Inject mock sklearn modules so RF tests run without scikit-learn installed."""
    rf_instance = MagicMock()
    rf_instance.predict.side_effect = lambda x: np.zeros(len(x), dtype=int)
    rf_instance.feature_importances_ = np.ones(20) / 20

    MockRF = MagicMock(return_value=rf_instance)

    cv_instance = MagicMock()
    cv_instance.split.return_value = [
        ([2, 3, 4, 5, 6, 7, 8, 9], [0, 1]),
        ([0, 1, 4, 5, 6, 7, 8, 9], [2, 3]),
        ([0, 1, 2, 3, 6, 7, 8, 9], [4, 5]),
        ([0, 1, 2, 3, 4, 5, 8, 9], [6, 7]),
        ([0, 1, 2, 3, 4, 5, 6, 7], [8, 9]),
    ]
    MockCV = MagicMock(return_value=cv_instance)

    mock_accuracy = MagicMock(return_value=0.8)
    mock_cm       = MagicMock(return_value=np.array([[4, 1], [1, 4]]))

    mod_ensemble         = MagicMock(); mod_ensemble.RandomForestClassifier = MockRF
    mod_model_selection  = MagicMock(); mod_model_selection.StratifiedKFold = MockCV
    mod_metrics          = MagicMock()
    mod_metrics.accuracy_score   = mock_accuracy
    mod_metrics.confusion_matrix = mock_cm

    monkeypatch.setitem(sys.modules, "sklearn",                  MagicMock())
    monkeypatch.setitem(sys.modules, "sklearn.ensemble",         mod_ensemble)
    monkeypatch.setitem(sys.modules, "sklearn.model_selection",  mod_model_selection)
    monkeypatch.setitem(sys.modules, "sklearn.metrics",          mod_metrics)

    return {"MockRF": MockRF, "rf_instance": rf_instance}


# ── /api/random_forest ────────────────────────────────────────────────────────

class TestRandomForestRoute:
    def test_sklearn_not_installed_returns_503(self, client):
        resp = client.post("/api/random_forest", json={})
        assert resp.status_code == 503
        assert "scikit-learn" in resp.get_json()["error"]

    def test_no_data_returns_503(self, sklearn_mocks, client):
        resp = client.post("/api/random_forest", json={})
        assert resp.status_code == 503
        assert "No data available" in resp.get_json()["error"]

    def test_too_few_records_returns_422(self, sklearn_mocks, client, tmp_base):
        records = _make_dataset(n_orig=2, n_alt=2)
        (tmp_base / "records.json").write_text(json.dumps(records), encoding="utf-8")
        resp = client.post("/api/random_forest", json={})
        assert resp.status_code == 422
        assert "Not enough" in resp.get_json()["error"]

    def test_valid_request_returns_200_with_expected_keys(self, sklearn_mocks, client, tmp_base):
        (tmp_base / "records.json").write_text(json.dumps(_make_dataset()), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 42})
        assert resp.status_code == 200
        body = resp.get_json()
        for key in ("n_original", "n_altered", "n_total", "seed", "fold_accuracies",
                    "mean_accuracy", "std_accuracy", "confusion_matrix", "feature_importances"):
            assert key in body

    def test_seed_echoed_in_response(self, sklearn_mocks, client, tmp_base):
        (tmp_base / "records.json").write_text(json.dumps(_make_dataset()), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 7})
        assert resp.get_json()["seed"] == 7

    def test_record_counts_correct(self, sklearn_mocks, client, tmp_base):
        (tmp_base / "records.json").write_text(json.dumps(_make_dataset(n_orig=6, n_alt=4)), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1})
        body = resp.get_json()
        assert body["n_original"] == 6
        assert body["n_altered"]  == 4
        assert body["n_total"]    == 10

    def test_selected_models_filters_altered_records(self, sklearn_mocks, client, tmp_base):
        records = (
            [_pixel_rec("p0", i) for i in range(5)]
            + [_pixel_rec("p2", i + 5, model="grok")   for i in range(5)]
            + [_pixel_rec("p2", i + 10, model="gemini") for i in range(5)]
        )
        (tmp_base / "records.json").write_text(json.dumps(records), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1, "models": ["grok"]})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["n_altered"] == 5
        assert body["selected_models"] == ["grok"]

    def test_records_missing_pixel_features_skipped(self, sklearn_mocks, client, tmp_base):
        complete   = _make_dataset(n_orig=5, n_alt=5)
        incomplete = [_pixel_rec("p0", 99, include_all_features=False)]
        (tmp_base / "records.json").write_text(json.dumps(complete + incomplete), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1})
        assert resp.status_code == 200
        assert resp.get_json()["n_total"] == 10

    def test_non_p0_p2_records_skipped(self, sklearn_mocks, client, tmp_base):
        records = _make_dataset() + [{"id": "p1rec", "type": "p1"}]
        (tmp_base / "records.json").write_text(json.dumps(records), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1})
        assert resp.status_code == 200
        assert resp.get_json()["n_total"] == 10

    def test_feature_set_indicators(self, sklearn_mocks, client, tmp_base):
        records = [_indicator_rec("p0", i) for i in range(5)] + \
                  [_indicator_rec("p2", i + 5) for i in range(5)]
        (tmp_base / "records.json").write_text(json.dumps(records), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1, "feature_set": "indicators"})
        assert resp.status_code == 200
        body = resp.get_json()
        feature_names = [f["feature"] for f in body["feature_importances"]]
        assert "has_camera_exif" in feature_names
        assert "ela_mean_diff" not in feature_names

    def test_feature_set_both(self, sklearn_mocks, client, tmp_base):
        records = [_indicator_rec("p0", i) for i in range(5)] + \
                  [_indicator_rec("p2", i + 5) for i in range(5)]
        (tmp_base / "records.json").write_text(json.dumps(records), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1, "feature_set": "both"})
        assert resp.status_code == 200
        body = resp.get_json()
        feature_names = [f["feature"] for f in body["feature_importances"]]
        assert "ela_mean_diff"   in feature_names
        assert "has_camera_exif" in feature_names

    def test_stratify_by_model(self, sklearn_mocks, client, tmp_base):
        records = (
            [_pixel_rec("p0", i) for i in range(5)]
            + [_pixel_rec("p2", i + 5, model="grok")   for i in range(3)]
            + [_pixel_rec("p2", i + 8, model="gemini") for i in range(2)]
        )
        (tmp_base / "records.json").write_text(json.dumps(records), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1, "stratify_by": "model"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["stratify_by"] == "model"

    def test_feature_importances_sorted_descending(self, sklearn_mocks, client, tmp_base):
        (tmp_base / "records.json").write_text(json.dumps(_make_dataset()), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1})
        importances = [f["importance"] for f in resp.get_json()["feature_importances"]]
        assert importances == sorted(importances, reverse=True)

    def test_fold_accuracies_length_matches_n_splits(self, sklearn_mocks, client, tmp_base):
        (tmp_base / "records.json").write_text(json.dumps(_make_dataset()), encoding="utf-8")
        resp = client.post("/api/random_forest", json={"seed": 1})
        assert len(resp.get_json()["fold_accuracies"]) == 5

    def test_supabase_path(self, sklearn_mocks, client, supabase_mock):
        supabase_mock.table.return_value.select.return_value.execute.return_value.data = [
            {"data": _pixel_rec("p0", i)} for i in range(5)
        ] + [
            {"data": _pixel_rec("p2", i + 5)} for i in range(5)
        ]
        resp = client.post("/api/random_forest", json={"seed": 1})
        assert resp.status_code == 200
