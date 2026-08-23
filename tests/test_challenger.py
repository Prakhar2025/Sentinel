"""Tests for the champion/challenger shadow model (docs/14)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.test_api import event_payload, make_settings

from sentinel.baselines import Row
from sentinel.challenger import CHALLENGER_VERSION, ChallengerModel, train_challenger_from_rows
from sentinel.features import feature_vector_from_raw
from sentinel.service import create_app
from sentinel.store import AuditStore
from sentinel.verdict import VerdictEngine

API_KEY = {"X-API-Key": "test-key"}


def row(fraud: bool, taint: float, group: str) -> Row:
    raw = {
        "device_identity_ratio": 6.0 if fraud else 1.0,
        "cross_merchant_fanout": 6 if fraud else 1,
        "taint": taint,
        "velocity_merchants_72h": 5 if fraud else 0,
        "burn_rotate": 1 if fraud else 0,
        "amount_band_hit": 1.0 if fraud else 0.0,
        "new_identity_fraction": 1.0 if fraud else 0.0,
    }
    return Row(features=feature_vector_from_raw(raw), is_fraud=fraud, group=group)


@pytest.fixture()
def small_challenger() -> ChallengerModel:
    train = [row(True, 1.0, "r1")] * 4 + [row(False, 0.0, "c1")] * 6
    return train_challenger_from_rows(train, "unit fixture")


class TestChallengerModel:
    def test_predict_shape(self, small_challenger: ChallengerModel) -> None:
        opinion = small_challenger.predict(row(True, 1.0, "r9").features)
        assert set(opinion) == {"score", "probability", "flag"}
        assert 0 <= opinion["score"] <= 100
        assert opinion["flag"] is (opinion["probability"] >= 0.5)

    def test_save_load_roundtrip(self, small_challenger: ChallengerModel, tmp_path: Path) -> None:
        path = tmp_path / "challenger.pkl"
        small_challenger.save(path)
        loaded = ChallengerModel.load(path)
        assert loaded is not None
        assert loaded.version == CHALLENGER_VERSION
        fresh = row(False, 0.0, "c9").features
        assert loaded.predict(fresh) == small_challenger.predict(fresh)

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert ChallengerModel.load(tmp_path / "absent.pkl") is None

    def test_load_stale_version_returns_none(
        self, small_challenger: ChallengerModel, tmp_path: Path
    ) -> None:
        import pickle

        path = tmp_path / "stale.pkl"
        with path.open("wb") as handle:
            pickle.dump({"model": small_challenger.model, "version": "ancient"}, handle)
        assert ChallengerModel.load(path) is None

    def test_load_corrupt_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "corrupt.pkl"
        path.write_bytes(b"not a pickle")
        assert ChallengerModel.load(path) is None


class TestShadowInService:
    def client(self, tmp_path: Path, challenger: ChallengerModel | None) -> TestClient:
        settings = make_settings(tmp_path, tmp_path / "spool")
        store = AuditStore(tmp_path / "audit.db")
        app = create_app(
            settings=settings,
            store=store,
            engine=VerdictEngine(),
            challenger=challenger,
        )
        return TestClient(app, raise_server_exceptions=False)

    def test_shadow_opinion_recorded(
        self, tmp_path: Path, small_challenger: ChallengerModel
    ) -> None:
        client = self.client(tmp_path, small_challenger)
        response = client.post("/v1/events", json=event_payload(1), headers=API_KEY)
        assert response.status_code == 200
        assert response.json()["challenger"] is not None
        stored = client.get("/v1/verdicts/evt-0001", headers=API_KEY).json()
        assert stored["challenger"]["score"] is not None

    def test_no_artifact_means_no_shadow(self, tmp_path: Path) -> None:
        client = self.client(tmp_path, None)
        response = client.post("/v1/events", json=event_payload(2), headers=API_KEY)
        assert response.status_code == 200
        assert response.json()["challenger"] is None

    def test_stale_artifact_disables_shadow(
        self, tmp_path: Path, small_challenger: ChallengerModel
    ) -> None:
        import pickle

        stale = tmp_path / "stale.pkl"
        with stale.open("wb") as handle:
            pickle.dump({"model": small_challenger.model, "version": "ancient"}, handle)
        settings = make_settings(tmp_path, tmp_path / "spool")
        settings.challenger_model_path = str(stale)
        app = create_app(
            settings=settings, store=AuditStore(tmp_path / "a.db"), engine=VerdictEngine()
        )
        client = TestClient(app, raise_server_exceptions=False)
        assert app.state.challenger is None
        response = client.post("/v1/events", json=event_payload(3), headers=API_KEY)
        assert response.status_code == 200


class TestStoreMigration:
    def test_old_verdicts_table_gains_challenger_column(self, tmp_path: Path) -> None:
        db = tmp_path / "old.db"
        store = AuditStore(db)
        # Simulate a pre-v2 database by dropping the new column.
        from sqlalchemy import text

        with store._engine.begin() as connection:
            connection.execute(text("ALTER TABLE verdicts DROP COLUMN challenger"))
        store.close()

        migrated = AuditStore(db)  # startup runs the migration
        from sqlalchemy import inspect

        columns = {c["name"] for c in inspect(migrated._engine).get_columns("verdicts")}
        assert "challenger" in columns
        migrated.close()
