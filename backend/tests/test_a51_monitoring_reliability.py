"""
ZWM v1.1.0 Block A5.1 — monitoring reliability.

Monitoring reads never start training, evaluation, activation, rollback or recovery;
an unreachable database yields 503 (no partial data, no writes); worker availability
is reported as online / offline / unavailable / unknown, never guessed.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import model_deployment_service as mds
from app.services import model_evaluation_service as mes
from app.services import monitoring_service as mon
from app.services import training_pipeline_service as tps
from test_a2_training_pipeline import no_real_training, worker  # noqa: F401
from test_a3_candidate_evaluation import _evaluator, _run, eval_dirs  # noqa: F401
from test_a4_model_deployment import ADMIN, _approve, cand, deploy_env  # noqa: F401
from test_a5_monitoring import _A5_ENDPOINTS, _codes, _fresh_heartbeats, _job, monitoring_env  # noqa: F401
from test_training_foundation import Session, api, db, engine, queued, three_cats, user  # noqa: F401

READ_URLS = [u for u in _A5_ENDPOINTS if "some-job" not in u] + [
    "/api/ml/approvals?decision=approved", "/api/ml/monitoring/timeline?offset=10",
    "/api/ml/candidates", "/api/ml/models", "/api/ml/deployments/events"]


class Tripwire(AssertionError):
    pass


@pytest.fixture()
def tripwires(monkeypatch):
    """Every operation that changes pipeline state raises if a monitoring read reaches it."""
    calls = []

    def trip(name):
        def _f(*a, **k):
            calls.append(name)
            raise Tripwire(f"monitoring read invoked {name}")
        return _f

    for mod, names in ((tps, ["dispatch_pending_training_jobs", "create_snapshot_training_job", "_send_to_queue",
                              "run_snapshot_job"]),
                       (mes, ["request_evaluation", "dispatch_pending_evaluations"]),
                       (mds, ["activate_model_version", "rollback", "run_deployment_maintenance",
                              "reconcile_serving_state", "approve_candidate", "reject_candidate"])):
        for n in names:
            if hasattr(mod, n):
                monkeypatch.setattr(mod, n, trip(f"{mod.__name__}.{n}"))
    return calls


def test_monitoring_reads_trigger_no_pipeline_operation(db, Session, cand, deploy_env, api, tripwires):
    mv, _ = cand
    _job(db, version="v-q", status="queued")
    _job(db, version="v-f", status="failed", attempt_count=3, error_message="boom")
    for _ in range(3):
        for u in READ_URLS:
            assert api.get(u).status_code == 200, u
    assert tripwires == []


@pytest.fixture()
def dead_db_api(api):
    """Same app, but every request gets a session on an unreachable database."""
    from app.database import get_db
    from app.main import app as fastapi_app
    dead = create_engine("postgresql://nobody:x@127.0.0.1:1/unreachable_test", pool_pre_ping=False,
                         connect_args={"connect_timeout": 2})
    DeadSession = sessionmaker(bind=dead)

    def _dead():
        s = DeadSession()
        try:
            yield s
        finally:
            s.close()

    fastapi_app.dependency_overrides[get_db] = _dead
    yield api
    dead.dispose()


@pytest.mark.parametrize("url", ["/api/ml/monitoring/summary", "/api/ml/monitoring/timeline"])
def test_unreachable_database_is_a_clean_503(dead_db_api, url):
    r = dead_db_api.get(url)
    assert r.status_code == 503
    body = r.text
    assert "temporarily unavailable" in body and "unreachable_test" not in body and "nobody" not in body


@pytest.mark.parametrize("probe,expected,severity", [
    ({"status": "online", "workers": ["celery@a"]}, "online", None),
    ({"status": "offline", "workers": []}, "offline", "critical"),        # pending work below
    ({"status": "unavailable", "workers": [], "error": "ConnectionError"}, "unavailable", "critical"),
])
def test_worker_states_are_reported_accurately(db, api, monitoring_env, probe, expected, severity):
    _fresh_heartbeats(db)
    _job(db, version="v-wait", status="queued")
    monitoring_env.clear()
    monitoring_env.update(probe)
    s = api.get("/api/ml/monitoring/summary").json()
    assert s["health"]["workers"]["status"] == expected
    alert = _codes(s["alerts"]).get("WORKER_UNAVAILABLE")
    assert (alert["severity"] if alert else None) == severity


def test_first_probe_timeout_reports_unknown_not_online(monkeypatch):
    import threading
    gate = threading.Event()
    monkeypatch.setattr(mon, "_probe_workers", lambda: (gate.wait(5), {"status": "online", "workers": ["x"]})[1])
    mon._WORKER_CACHE.update(at=0.0, value=None)
    mon._PROBE["thread"] = None
    out = mon.worker_status(now_monotonic=1000.0, wait=0.05)
    gate.set()
    mon._PROBE["thread"] and mon._PROBE["thread"].join(5)
    assert out["status"] == "unknown" and out["refreshing"]
