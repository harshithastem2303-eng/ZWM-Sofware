"""
Block A1.3 — admin settings endpoints require admin authorization.

Uses conftest's client/auth fixtures (which TRUNCATE the DATABASE_URL database),
so this module only runs against a database whose name contains "test".
"""
import pytest

from app.config import settings
from app.models.setting import SystemSetting
from test_a1_integration import _annotate, _finalize, _readiness, _snapshots, _RECTS, no_training  # noqa: F401
from test_annotations import _create_category, _upload_image

pytestmark = pytest.mark.skipif(
    "test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
    reason="security test only runs against an isolated *test* database",
)

_SETTINGS_KEYS = {
    "platform_name", "admin_email", "api_base_url", "maintenance_mode", "active_model",
    "epochs", "image_size", "batch_size", "device", "optimizer", "learning_rate",
    "auto_retrain_count", "confidence_threshold", "auto_train_toggle",
}


def _stored_threshold(db):
    db.expire_all()
    row = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    return row.auto_retrain_count if row else None


@pytest.fixture()
def real_admin_headers(client):
    """Token from the existing admin login flow (admins table / configured admin)."""
    r = client.post("/api/admin/login", json={
        "email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD,
    })
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def known_threshold(client, real_admin_headers, db):
    r = client.put("/api/admin/settings", json={"auto_retrain_count": 777}, headers=real_admin_headers)
    assert r.status_code == 200
    assert _stored_threshold(db) == 777
    return 777


class TestAdminSettingsAuthorization:
    def test_unauthenticated_get_rejected(self, client):
        assert client.get("/api/admin/settings").status_code == 401

    def test_unauthenticated_put_rejected_and_no_change(self, client, db, known_threshold):
        r = client.put("/api/admin/settings", json={"auto_retrain_count": 5})
        assert r.status_code == 401
        assert _stored_threshold(db) == known_threshold

    def test_invalid_token_rejected(self, client, db, known_threshold):
        bad = {"Authorization": "Bearer not-a-real-token"}
        assert client.get("/api/admin/settings", headers=bad).status_code == 401
        assert client.put("/api/admin/settings", json={"auto_retrain_count": 5}, headers=bad).status_code == 401
        assert _stored_threshold(db) == known_threshold

    def test_normal_user_rejected_and_no_change(self, client, user_auth, db, known_threshold):
        h = user_auth["headers"]
        assert client.get("/api/admin/settings", headers=h).status_code == 403
        assert client.put("/api/admin/settings", json={"auto_retrain_count": 5}, headers=h).status_code == 403
        assert _stored_threshold(db) == known_threshold

    def test_admin_login_get_and_put(self, client, real_admin_headers, db):
        r = client.get("/api/admin/settings", headers=real_admin_headers)
        assert r.status_code == 200
        assert _SETTINGS_KEYS <= set(r.json())                    # response shape unchanged

        r = client.put("/api/admin/settings", json={"auto_retrain_count": 250, "epochs": 30},
                       headers=real_admin_headers)
        assert r.status_code == 200
        assert r.json()["auto_retrain_count"] == 250 and r.json()["epochs"] == 30
        assert _stored_threshold(db) == 250

    def test_users_table_admin_role_still_allowed(self, client, admin_auth):
        assert client.get("/api/admin/settings", headers=admin_auth["headers"]).status_code == 200

    @pytest.mark.parametrize("payload", [
        {"auto_retrain_count": 0},
        {"auto_retrain_count": -5},
        {"auto_retrain_count": "abc"},
        {"epochs": "many"},
        {"maintenance_mode": "maybe"},
    ])
    def test_invalid_payload_rejected_without_change(self, client, real_admin_headers, db, known_threshold, payload):
        before = client.get("/api/admin/settings", headers=real_admin_headers).json()
        r = client.put("/api/admin/settings", json=payload, headers=real_admin_headers)
        assert r.status_code == 422
        assert client.get("/api/admin/settings", headers=real_admin_headers).json() == before
        assert _stored_threshold(db) == known_threshold


class TestSettingsDriveTrainingFoundation:
    def test_readiness_uses_admin_threshold_and_snapshot_still_works(
        self, client, real_admin_headers, admin_auth, user_auth, db
    ):
        ah, uh = admin_auth["headers"], user_auth["headers"]
        assert client.put("/api/admin/settings", json={"auto_retrain_count": 1},
                          headers=real_admin_headers).status_code == 200
        before = _readiness(client, ah)
        assert before["threshold"] == 1
        snaps_before = len(_snapshots(client, ah))

        cat = _create_category(client, ah)
        img = _upload_image(client, uh, seed=9401)
        for rect in _RECTS[:2]:
            assert _annotate(client, uh, img, cat, rect).status_code == 201
        assert len(_snapshots(client, ah)) == snaps_before          # nothing before finalize
        assert _finalize(client, uh, img).status_code == 200

        after = _readiness(client, ah)
        assert after["total_training_eligible_images"] == before["total_training_eligible_images"] + 1
        snaps = _snapshots(client, ah)
        assert len(snaps) >= snaps_before + 1
        assert snaps[-1]["dataset_size"] == after["last_milestone"]
        ids = client.get(f"/api/dataset/snapshots/{snaps[-1]['snapshot_id']}/images", headers=ah).json()["image_ids"]
        assert img in ids
