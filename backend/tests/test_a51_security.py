"""
ZWM v1.1.0 Block A5.1 — credential and path-exposure hardening.

No built-in admin/demo credentials or database password, opt-in bootstrap admin with
constant-time comparison, production validation, and no absolute filesystem paths
from the A3/A4 model APIs.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app import config as cfg
from app.config import Settings, settings
from app.services import model_deployment_service as mds  # noqa: F401
from test_a2_training_pipeline import no_real_training, worker  # noqa: F401
from test_a3_candidate_evaluation import _evaluator, _run, eval_dirs  # noqa: F401
from test_a4_model_deployment import ADMIN, _approve, _evaluate, _new_candidate, cand, deploy_env  # noqa: F401
from test_training_foundation import Session, api, db, engine, queued, three_cats, user  # noqa: F401

BACKEND = Path(__file__).resolve().parents[1]
ABS_PATH = re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:\\|(?<![\w.])/(?:tmp|home|Users|var|usr|private)/")
OLD_DEFAULTS = [("admin@gmail.com", "user123")]


def _settings(**kw):
    base = {"DATABASE_URL": "postgresql://u:p@h/x_test", "ADMIN_EMAIL": "", "ADMIN_PASSWORD": "",
            "DEMO_USER_EMAIL": "", "DEMO_USER_PASSWORD": "", "APP_ENV": "development"}
    return Settings(_env_file=None, **{**base, **kw})


class TestNoBuiltInSecrets:
    @pytest.mark.parametrize("field", ["ADMIN_EMAIL", "ADMIN_PASSWORD", "DATABASE_URL", "DEMO_USER_PASSWORD",
                                       "SECRET_KEY", "JWT_SECRET_KEY"])
    def test_defaults_are_empty(self, field):
        assert Settings.model_fields[field].default == ""

    def test_no_hardcoded_credentials_in_source(self):
        files = [BACKEND / "app" / "config.py", BACKEND / "app" / "main.py", BACKEND / "app" / "routes" / "admin.py",
                 BACKEND / "app" / "routes" / "auth.py", BACKEND / "scratch" / "clear_connections.py",
                 BACKEND / "scratch" / "seed_data.py", BACKEND.parent / "frontend" / "src" / "pages" / "AdminLogin.jsx"]
        for f in files:
            src = f.read_text(encoding="utf-8")
            assert not re.search(r"postgresql://[^:'\"$]+:[^@'\"${]+@", src), f          # no user:password@ URL
            assert "'admin@gmail.com'" not in src and '"admin@gmail.com"' not in src, f
            assert "password123\")" not in src and "'user123'" not in src, f

    def test_compose_requires_secrets(self):
        compose = (BACKEND.parent / "docker-compose.yml").read_text(encoding="utf-8")
        for var in ("POSTGRES_PASSWORD", "JWT_SECRET_KEY", "SECRET_KEY"):
            assert "${" + var + ":-" not in compose
            assert "${" + var + ":?" in compose


class TestConfigurationValidation:
    def test_missing_database_url_is_fatal(self):
        assert any("DATABASE_URL" in p for p in cfg.security_problems(_settings(DATABASE_URL="")))

    def test_half_configured_admin_is_fatal(self):
        assert cfg.security_problems(_settings(ADMIN_EMAIL="a@example.com"))
        assert cfg.security_problems(_settings(ADMIN_PASSWORD="x" * 20))

    @pytest.mark.parametrize("pw", ["user123", "password123", "short", "Admin123"])
    def test_production_rejects_weak_admin_password(self, pw):
        s = _settings(APP_ENV="production", ADMIN_EMAIL="a@example.com", ADMIN_PASSWORD=pw)
        assert any("ADMIN_PASSWORD" in p for p in cfg.security_problems(s))

    def test_production_rejects_demo_account_and_accepts_strong_config(self):
        strong = "Vq3!rT9#mW2$kL8@"
        assert cfg.security_problems(_settings(APP_ENV="production", ADMIN_EMAIL="a@example.com",
                                               ADMIN_PASSWORD=strong, DEMO_USER_PASSWORD="demo-pass-1234"))
        assert cfg.security_problems(_settings(APP_ENV="production", ADMIN_EMAIL="a@example.com",
                                               ADMIN_PASSWORD=strong)) == []
        assert cfg.security_problems(_settings(APP_ENV="production")) == []     # admins-table-only deployments

    def test_development_weak_password_only_warns(self):
        s = _settings(ADMIN_EMAIL="a@example.com", ADMIN_PASSWORD="user123")
        assert cfg.security_problems(s) == [] and cfg.security_warnings(s)

    @pytest.mark.parametrize("env,needle", [
        ({"DATABASE_URL": ""}, "DATABASE_URL must be set"),
        ({"APP_ENV": "production", "ADMIN_EMAIL": "a@example.com", "ADMIN_PASSWORD": "user123",
          "SECRET_KEY": "s" * 40, "JWT_SECRET_KEY": "j" * 40}, "ADMIN_PASSWORD must be at least"),
    ])
    def test_application_refuses_to_start(self, env, needle):
        child_env = {**os.environ, **env}
        r = subprocess.run([sys.executable, "-c", "import app.config"], cwd=BACKEND, env=child_env,
                           capture_output=True, text=True, timeout=120)
        assert r.returncode != 0 and needle in r.stderr, r.stderr[-500:]


class TestBootstrapAdmin:
    def test_unconfigured_admin_never_matches(self):
        s = _settings()
        assert not cfg.env_admin_configured(s)
        for email, pw in [("", ""), ("admin@gmail.com", "user123"), (" ", " ")]:
            assert not cfg.env_admin_matches(email, pw, s)

    def test_configured_admin_matches_exactly(self):
        s = _settings(ADMIN_EMAIL="Boot@Example.com", ADMIN_PASSWORD="Vq3!rT9#mW2$kL8@")
        assert cfg.env_admin_matches("boot@example.com", "Vq3!rT9#mW2$kL8@", s)
        assert not cfg.env_admin_matches("boot@example.com", "Vq3!rT9#mW2$kL8", s)
        assert not cfg.env_admin_matches("other@example.com", "Vq3!rT9#mW2$kL8@", s)

    def test_session_bootstrap_admin_logs_in(self, client):
        r = client.post("/api/admin/login", json={"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD})
        assert r.status_code == 200 and r.json()["role"] == "admin"
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert client.get("/api/ml/monitoring/timeline?limit=1", headers=h).status_code == 200

    @pytest.mark.parametrize("email,pw", OLD_DEFAULTS)
    def test_former_default_credentials_are_rejected(self, client, email, pw):
        assert client.post("/api/admin/login", json={"email": email, "password": pw}).status_code == 401
        assert client.post("/api/auth/login", json={"email": email, "password": pw}).status_code == 401
        assert client.post("/api/auth/token", data={"username": email, "password": pw}).status_code == 401

    def test_empty_credentials_are_rejected(self, client):
        for body in ({"email": "", "password": ""}, {"email": settings.ADMIN_EMAIL, "password": ""}):
            assert client.post("/api/admin/login", json=body).status_code in (401, 422)

    def test_disabled_bootstrap_admin_cannot_log_in(self, client, monkeypatch):
        email, pw = settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD
        monkeypatch.setattr(settings, "ADMIN_EMAIL", "")
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
        r = client.post("/api/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 401

    def test_startup_seeding_is_opt_in(self, monkeypatch):
        from app import main
        from app.database import SessionLocal
        from app.models.user import Admin, User
        monkeypatch.setattr(settings, "ADMIN_EMAIL", "")
        monkeypatch.setattr(settings, "ADMIN_PASSWORD", "")
        monkeypatch.setattr(settings, "DEMO_USER_EMAIL", "demo-a51@example.com")
        monkeypatch.setattr(settings, "DEMO_USER_PASSWORD", "")              # email alone seeds nothing
        main.init_db_and_seed()
        db = SessionLocal()
        try:
            assert db.query(User).filter(User.email.in_(["admin@gmail.com", "keerthana@zwm.eco",
                                                          "demo-a51@example.com"])).count() == 0
            assert db.query(Admin).filter(Admin.admin_email == "admin@gmail.com").count() == 0
        finally:
            db.close()


class TestNoAbsolutePathsFromModelApis:
    def test_public_paths_helper(self):
        from app.services.monitoring_service import public_paths
        out = public_paths({"weights_path": r"C:\a\b\best.pt", "dataset_manifest_path": "/tmp/x/manifest.json",
                            "nested": [{"model_path": "/home/u/m.pt", "error_message": "open /var/lib/x.pt failed"}],
                            "path_count": 3, "version": "v1"})
        assert out == {"weights_path": "best.pt", "dataset_manifest_path": "manifest.json",
                       "nested": [{"model_path": "m.pt", "error_message": "open <path>/x.pt failed"}],
                       "path_count": 3, "version": "v1"}

    def test_evaluation_detail_candidates_and_models(self, db, Session, cand, api):
        mv, _ = cand
        ev = _evaluate(db, Session, mv)
        detail = api.get(f"/api/ml/evaluations/{ev.evaluation_id}").json()
        assert detail["weights_path"] == Path(ev.weights_path).name
        assert detail["dataset_manifest_path"] == Path(ev.dataset_manifest_path).name
        assert detail["metrics"] and detail["gate_results"] is not None                  # content preserved
        payloads = [detail, api.get("/api/ml/candidates").json(), api.get("/api/ml/models").json(),
                    api.get(f"/api/ml/models/{mv.model_id}").json(), api.get("/api/ml/deployments").json()]
        for p in payloads:
            assert not ABS_PATH.search(json.dumps(p)), ABS_PATH.search(json.dumps(p))
