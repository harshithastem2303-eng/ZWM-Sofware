"""
ZWM v1.1.0 Block A5 — administrator monitoring, attempt history, scheduler heartbeats.

Isolation as in A1-A4.1: own database (SQLite per test or the throwaway PostgreSQL
database from ZWM_A1_TEST_DATABASE_URL), synthetic weights under tmp_path, fake
trainers/evaluators/loaders, ultralytics.YOLO replaced by a raising stub.
"""
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, text

from app.config import settings
from app.database import Base
from app.models.training import (
    DeploymentRecordImmutableError,
    ModelEvaluation,
    SchedulerHeartbeat,
    TrainingJob,
    TrainingJobEvent,
)
from app.services import monitoring_service as mon
from app.services import model_deployment_service as mds
from app.services import training_pipeline_service as tps
from test_a2_training_pipeline import no_real_training, worker  # noqa: F401
from test_a3_candidate_evaluation import _evaluator, _run, eval_dirs  # noqa: F401
from test_a4_model_deployment import (  # noqa: F401
    ADMIN, _approve, _evaluate, _new_candidate, cand, deploy_env,
)
from test_training_foundation import (  # noqa: F401
    Session, api, db, engine, queued, three_cats, user, _complete_many, _set_threshold,
)

NOW = lambda: datetime.now(timezone.utc)                                    # noqa: E731
ABS_PATH = re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:\\|(?<![\w.])/(?:tmp|home|Users|var|usr|private)/")


@pytest.fixture(autouse=True)
def monitoring_env(monkeypatch):
    """Workers 'online' by default (no broker in tests); the probe cache never leaks between tests."""
    state = {"status": "online", "workers": ["celery@test"]}
    monkeypatch.setattr(mon, "_probe_workers", lambda: dict(state))
    mon._WORKER_CACHE.update(at=0.0, value=None)
    mon._PROBE["thread"] = None
    yield state
    if mon._PROBE["thread"] is not None:
        mon._PROBE["thread"].join(5)
    mon._WORKER_CACHE.update(at=0.0, value=None)
    mon._PROBE["thread"] = None


def _fresh_heartbeats(db, now=None):
    now = now or NOW()
    from app.services.cleanup_worker import SCHEDULER_JOBS
    for name, interval in SCHEDULER_JOBS.items():
        db.merge(SchedulerHeartbeat(job_name=name, interval_seconds=int(interval()), last_status="ok",
                                    last_started_at=now, last_finished_at=now, run_count=1, consecutive_failures=0))
    db.commit()


def _job(db, **fields):
    defaults = {"version": "v-mon", "status": "queued", "trigger": "manual"}
    job = TrainingJob(**{**defaults, **fields})
    db.add(job)
    db.commit()
    return job


def _codes(alerts):
    return {a["code"]: a for a in alerts}


def _events(db, job_id):
    db.expire_all()
    return db.query(TrainingJobEvent).filter(TrainingJobEvent.job_id == job_id).all()


def _table_state(db, serving: Path):
    db.expire_all()
    counts = {t.name: db.execute(text(f"SELECT COUNT(*) FROM {t.name}")).scalar() for t in Base.metadata.sorted_tables}
    db.rollback()
    return counts, serving.read_bytes() if serving.exists() else None


# ---------------------------------------------------------------------------
# Append-only attempt history
# ---------------------------------------------------------------------------

class TestAttemptHistory:
    def test_snapshot_job_lifecycle_is_recorded(self, db, user, tmp_path, three_cats, worker, deploy_env):
        mv, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "H1")
        events = _events(db, mv.job_id)
        kinds = [e.event_type for e in events]
        assert {"created", "claimed", "completed"} <= set(kinds)
        claimed = next(e for e in events if e.event_type == "claimed")
        assert claimed.attempt == 1 and claimed.status_before == "queued" and claimed.status_after == "running"
        assert claimed.worker_id

    def test_retry_requeue_and_exhaustion_are_recorded(self, db):
        job = _job(db)
        for attempt in range(1, settings.TRAINING_MAX_ATTEMPTS + 1):
            job.status, job.attempt_count, job.worker_id = "running", attempt, f"w{attempt}"
            db.commit()
            if attempt < settings.TRAINING_MAX_ATTEMPTS:
                job.status, job.error_message = "queued", r"attempt crashed in C:\secret\runs\best.pt"
            else:
                job.status, job.error_message = "failed", "training crashed; retry limit reached"
            job.worker_id = None
            db.commit()
        kinds = [e.event_type for e in sorted(_events(db, job.job_id), key=lambda e: (e.attempt or 0, e.event_type))]
        assert kinds.count("claimed") == settings.TRAINING_MAX_ATTEMPTS
        assert kinds.count("requeued") == settings.TRAINING_MAX_ATTEMPTS - 1
        assert kinds.count("retries_exhausted") == 1 and "created" in kinds
        requeued = [e for e in _events(db, job.job_id) if e.event_type == "requeued"]
        assert all(e.message and "crashed" in e.message for e in requeued)

    def test_dispatch_success_and_failure_are_recorded(self, db, user, tmp_path, three_cats, monkeypatch):
        a, b, c = three_cats
        _set_threshold(db, 5)
        _complete_many(db, user, [(a, 5)], tmp_path)
        [job] = db.query(TrainingJob).filter(TrainingJob.snapshot_id.isnot(None)).all()
        monkeypatch.setattr(tps, "_send_to_queue", lambda job_id: (_ for _ in ()).throw(ConnectionError("broker down")))
        tps.dispatch_pending_training_jobs(db)
        monkeypatch.setattr(tps, "_send_to_queue", lambda job_id: "task-1")
        tps.dispatch_pending_training_jobs(db)
        kinds = {e.event_type: e for e in _events(db, job.job_id)}
        assert "dispatch_failed" in kinds and "broker down" in kinds["dispatch_failed"].message
        assert "dispatched" in kinds and kinds["dispatched"].dispatch_attempts == 2

    def test_history_is_append_only(self, db):
        job = _job(db)
        [event] = _events(db, job.job_id)
        event.message = "tampered"
        with pytest.raises(DeploymentRecordImmutableError):
            db.commit()
        db.rollback()
        db.delete(db.query(TrainingJobEvent).first())
        with pytest.raises(DeploymentRecordImmutableError):
            db.commit()
        db.rollback()

    def test_job_detail_api_returns_redacted_history(self, db, api):
        job = _job(db)
        job.status, job.attempt_count = "running", 1
        db.commit()
        job.status, job.error_message = "queued", r"failed reading C:\Users\admin\secret\data.yaml"
        db.commit()
        body = api.get(f"/api/ml/jobs/{job.job_id}").json()
        assert [e["event_type"] for e in body["history"]].count("requeued") == 1
        assert "secret" not in json.dumps(body) and "data.yaml" in json.dumps(body)


# ---------------------------------------------------------------------------
# Persisted scheduler heartbeats
# ---------------------------------------------------------------------------

class TestSchedulerHeartbeat:
    @pytest.fixture()
    def sched(self, monkeypatch, Session):
        from app.services import cleanup_worker
        monkeypatch.setattr(cleanup_worker, "SessionLocal", Session)
        return cleanup_worker

    def test_successful_runs_are_persisted(self, db, sched):
        job = sched._tracked("training_dispatch", lambda: 60)(lambda: None)
        job()
        job()
        db.expire_all()
        row = db.get(SchedulerHeartbeat, "training_dispatch")
        assert (row.last_status, row.run_count, row.consecutive_failures, row.interval_seconds) == ("ok", 2, 0, 60)
        assert row.last_finished_at and row.last_duration_seconds is not None and row.process_id

    def test_failures_are_persisted_contained_and_alerted(self, db, sched, api):
        def boom():
            raise RuntimeError(r"cannot open C:\models\secret\best.pt")
        failing = sched._tracked("deployment_recovery", lambda: 60)(boom)
        for _ in range(3):
            failing()                                                       # never raises into APScheduler
        db.expire_all()
        row = db.get(SchedulerHeartbeat, "deployment_recovery")
        assert (row.last_status, row.consecutive_failures, row.run_count) == ("error", 3, 3)
        alert = _codes(api.get("/api/ml/monitoring/summary").json()["alerts"])["SCHEDULER_JOB_FAILING"]
        assert alert["severity"] == "critical" and "secret" not in alert["message"]
        sched._tracked("deployment_recovery", lambda: 60)(lambda: None)()
        db.expire_all()
        assert db.get(SchedulerHeartbeat, "deployment_recovery").consecutive_failures == 0

    def test_real_scheduler_job_records_heartbeat(self, db, sched, deploy_env):
        sched._deployment_recovery_job()
        db.expire_all()
        row = db.get(SchedulerHeartbeat, "deployment_recovery")
        assert row.last_status == "ok" and row.interval_seconds == settings.DEPLOYMENT_RECOVERY_INTERVAL_SECONDS

    def test_stale_and_missing_heartbeats_are_alerted(self, db, api):
        _fresh_heartbeats(db)
        old = NOW() - timedelta(hours=1)
        row = db.get(SchedulerHeartbeat, "deployment_recovery")
        row.last_finished_at = old
        db.delete(db.get(SchedulerHeartbeat, "image_cleanup"))
        db.commit()
        alerts = _codes(api.get("/api/ml/monitoring/summary").json()["alerts"])
        assert alerts["SCHEDULER_STALE"]["severity"] == "critical"
        assert "SCHEDULER_NEVER_RAN" in alerts


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_healthy_system_has_no_alerts_beyond_info(self, db, api):
        _fresh_heartbeats(db)
        alerts = api.get("/api/ml/monitoring/summary").json()["alerts"]
        assert [a["code"] for a in alerts] == ["NO_ACTIVE_MODEL"] and alerts[0]["severity"] == "info"

    def test_expired_lease_and_abandoned_job(self, db, api):
        _fresh_heartbeats(db)
        grace = settings.TRAINING_LEASE_GRACE_SECONDS
        _job(db, version="v-exp", status="running", attempt_count=1, worker_id="w",
             lease_expires_at=NOW() - timedelta(seconds=10))
        _job(db, version="v-abn", status="running", attempt_count=2, worker_id="w",
             lease_expires_at=NOW() - timedelta(seconds=grace + 60))
        alerts = [a for a in api.get("/api/ml/monitoring/summary").json()["alerts"] if a["code"] == "JOB_LEASE_EXPIRED"]
        assert sorted(a["severity"] for a in alerts) == ["critical", "warning"]

    def test_stuck_and_dispatch_failing_jobs(self, db, api):
        old = NOW() - timedelta(minutes=settings.TRAINING_DISPATCH_STALE_MINUTES + 5)
        _job(db, version="v-stuck", status="queued", created_at=old, dispatched_at=old)
        snap_job = _job(db, version="v-noq", status="queued", dispatch_attempts=3)
        snap_job.snapshot_id = None
        db.commit()
        from app.models.training import TrainingSnapshot
        snap = TrainingSnapshot(version=99, threshold=1, milestone_count=999, dataset_size=1, class_map=[], status="locked")
        db.add(snap)
        db.commit()
        _job(db, version="v-dispatch", status="queued", dispatch_attempts=3, snapshot_id=snap.snapshot_id)
        alerts = _codes(api.get("/api/ml/monitoring/summary").json()["alerts"])
        assert alerts["JOB_STUCK"]["severity"] == "warning"
        assert alerts["JOB_DISPATCH_FAILING"]["severity"] == "critical"

    def test_exhausted_retries_and_failed_jobs(self, db, api):
        _job(db, version="v-dead", status="failed", attempt_count=settings.TRAINING_MAX_ATTEMPTS,
             completed_at=NOW(), error_message="retry limit reached")
        _job(db, version="v-oops", status="failed", attempt_count=1, completed_at=NOW(), error_message="bad dataset")
        _job(db, version="v-ancient", status="failed", attempt_count=1, completed_at=NOW() - timedelta(days=30))
        alerts = api.get("/api/ml/monitoring/summary").json()["alerts"]
        codes = [a["code"] for a in alerts]
        assert codes.count("JOB_RETRIES_EXHAUSTED") == 1 and codes.count("JOB_FAILED") == 1   # old failures age out

    def test_evaluation_failure_is_alerted(self, db, Session, cand, api):
        mv, _ = cand

        def broken(*a, **k):
            raise RuntimeError("evaluator crashed")

        ev = _evaluate(db, Session, mv, broken)
        assert ev.status == "error"
        alert = _codes(api.get("/api/ml/monitoring/summary").json()["alerts"])["EVALUATION_FAILED"]
        assert alert["evaluation_id"] == ev.evaluation_id

    def test_inconsistent_deployment_and_unavailable_workers(self, db, Session, cand, deploy_env, api, monitoring_env):
        mv, _ = cand
        _approve(db, Session, mv)
        mds.activate_model_version(db, mv.model_id, ADMIN)
        deploy_env.serving.write_bytes(b"DRIFTED")
        _job(db, version="v-wait", status="queued")
        monitoring_env["status"], monitoring_env["workers"] = "offline", []
        alerts = _codes(api.get("/api/ml/monitoring/summary").json()["alerts"])
        assert alerts["DEPLOYMENT_INCONSISTENT"]["severity"] == "critical"
        assert alerts["WORKER_UNAVAILABLE"]["severity"] == "critical" and "waiting" in alerts["WORKER_UNAVAILABLE"]["message"]
        assert deploy_env.serving.read_bytes() == b"DRIFTED"                 # alerting never repairs

    def test_worker_probe_is_cached_and_never_blocks(self, monkeypatch):
        import time as _time
        calls = []

        def slow_probe():
            calls.append(1)
            _time.sleep(2.0)                                              # unreachable broker
            return {"status": "offline", "workers": []}

        monkeypatch.setattr(mon, "_probe_workers", slow_probe)
        mon._WORKER_CACHE.update(at=0.0, value=None)
        mon._PROBE["thread"] = None
        t0 = _time.monotonic()
        first = mon.worker_status(now_monotonic=1000.0, wait=0.2)
        assert first["status"] == "unknown" and _time.monotonic() - t0 < 1.0    # request not blocked
        again = mon.worker_status(now_monotonic=1000.5, wait=0.2)          # probe still running: not restarted
        assert again["status"] == "unknown" and len(calls) == 1
        mon._PROBE["thread"].join(5)
        cached = mon.worker_status(now_monotonic=1010.0)
        assert (cached["status"], cached["cached"]) == ("offline", True)
        t1 = _time.monotonic()
        stale = mon.worker_status(now_monotonic=1000.0 + mon.WORKER_CACHE_SECONDS + 1)
        assert stale["status"] == "offline" and stale["refreshing"] and _time.monotonic() - t1 < 0.5
        mon._PROBE["thread"].join(5)
        assert len(calls) == 2


# ---------------------------------------------------------------------------
# Summary, timeline, pagination, redaction
# ---------------------------------------------------------------------------

class TestSummaryTimelineAndLists:
    def test_summary_reflects_pipeline_state(self, db, Session, user, tmp_path, three_cats, worker, deploy_env, api):
        v1, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "S1")
        _approve(db, Session, v1)
        mds.activate_model_version(db, v1.model_id, ADMIN)
        v2, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "S2")
        _evaluate(db, Session, v2)
        s = api.get("/api/ml/monitoring/summary").json()
        assert s["training"]["by_status"]["completed"] == 2
        assert s["dataset"]["snapshot_count"] == 2 and s["dataset"]["threshold"] == 30
        assert s["evaluations"]["by_status"]["passed"] == 2
        assert s["approvals"]["pending_count"] == 1 and s["approvals"]["pending"][0]["model_id"] == v2.model_id
        assert s["deployment"]["active_model"]["model_id"] == v1.model_id
        assert s["deployment"]["consistency"]["state"] == "consistent"
        assert "serving_sha256" not in s["deployment"]["consistency"]
        assert s["health"]["workers"]["status"] == "online"

    def test_no_absolute_paths_in_monitoring_responses(self, db, Session, user, tmp_path, three_cats, worker,
                                                       deploy_env, api):
        v1, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "P1")
        _approve(db, Session, v1)
        mds.activate_model_version(db, v1.model_id, ADMIN)
        job = db.query(TrainingJob).filter(TrainingJob.job_id == v1.job_id).one()
        payloads = [api.get("/api/ml/monitoring/summary").json(), api.get("/api/ml/monitoring/timeline").json(),
                    api.get("/api/ml/jobs").json(), api.get(f"/api/ml/jobs/{job.job_id}").json(),
                    api.get("/api/ml/deployments").json()]
        for payload in payloads:
            text_ = json.dumps(payload)
            assert str(tmp_path) not in text_ and str(tmp_path).replace("\\", "\\\\") not in text_
            assert not ABS_PATH.search(text_), ABS_PATH.search(text_)
        assert api.get("/api/ml/jobs").json()["jobs"][0]["best_model_path"] == Path(job.best_model_path).name

    def test_evaluation_and_deployment_lists_redact_error_paths(self, db, Session, cand, api):
        from app.models.training import ModelDeployment
        mv, _ = cand
        ev = _evaluate(db, Session, mv)
        ev.error_message = r"evaluator crashed reading C:\Users\owner\eval\best.pt"
        db.add(ModelDeployment(kind="activation", status="failed", model_id=mv.model_id, model_version=mv.version,
                               weights_sha256="0" * 64, error_message="copy to /home/owner/models/best.pt failed",
                               reason="see /var/lib/zwm/notes.txt"))
        db.commit()
        evs = api.get("/api/ml/evaluations?limit=5").json()["evaluations"]
        deps = api.get("/api/ml/deployments?limit=5").json()
        assert evs[0]["error_message"] == "evaluator crashed reading <path>/best.pt"
        assert deps["history"][0]["error_message"] == "copy to <path>/best.pt failed"
        assert deps["history"][0]["reason"] == "see <path>/notes.txt"
        for payload in (evs, deps, api.get("/api/ml/monitoring/summary").json()):
            assert not ABS_PATH.search(json.dumps(payload)), ABS_PATH.search(json.dumps(payload))

    def test_redact_helper(self):
        assert mon.redact(r"open C:\Users\x\models\best.pt failed") == "open <path>/best.pt failed"
        assert mon.redact("open /home/x/models/best.pt failed") == "open <path>/best.pt failed"
        assert mon.redact("plain message, ratio 3/4") == "plain message, ratio 3/4"
        assert mon.basename(r"C:\a\b\c.pt") == "c.pt" and mon.basename("/a/b/c.pt") == "c.pt"

    def test_jobs_pagination_and_filters(self, db, api):
        for i in range(12):
            _job(db, version=f"v{i:02d}", status="failed" if i % 3 == 0 else "completed")
        all_jobs = api.get("/api/ml/jobs").json()
        assert all_jobs["total"] == 12 and len(all_jobs["jobs"]) == 12                     # legacy default: all rows
        p1 = api.get("/api/ml/jobs?limit=5&offset=0").json()
        p2 = api.get("/api/ml/jobs?limit=5&offset=5").json()
        p3 = api.get("/api/ml/jobs?limit=5&offset=10").json()
        ids = [j["job_id"] for p in (p1, p2, p3) for j in p["jobs"]]
        assert len(ids) == 12 and len(set(ids)) == 12 and p3["total"] == 12
        failed = api.get("/api/ml/jobs?status=failed").json()
        assert failed["total"] == 4 and {j["status"] for j in failed["jobs"]} == {"failed"}
        assert api.get("/api/ml/jobs?status=bogus").status_code == 422
        assert api.get("/api/ml/jobs?limit=500").status_code == 422
        assert api.get("/api/ml/jobs?offset=-1").status_code == 422

    def test_evaluations_and_deployments_pagination(self, db, Session, cand, api):
        mv, _ = cand
        _evaluate(db, Session, mv)
        r = api.get("/api/ml/evaluations?limit=1&status=passed").json()
        assert r["total"] == 1 and len(r["evaluations"]) == 1
        assert r["evaluations"][0]["metrics"]["map50"] == 0.81                    # headline metrics in list items
        assert api.get("/api/ml/evaluations?status=nope").status_code == 422
        d = api.get("/api/ml/deployments?limit=1&offset=0").json()
        assert d["limit"] == 1 and d["total"] == 0 and d["history"] == []
        assert api.get("/api/ml/deployments?limit=0").status_code == 422

    def test_approval_records_pagination_and_filter(self, db, Session, user, tmp_path, three_cats, worker, cand, api):
        mv, _ = cand
        _approve(db, Session, mv)
        other, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "B")
        ev = _evaluate(db, Session, other)
        mds.reject_candidate(db, other.model_id, ev.evaluation_id, ADMIN, "not good enough")
        legacy = api.get("/api/ml/approvals").json()
        assert legacy["total"] == 2 and len(legacy["approvals"]) == 2                      # legacy default: all rows
        p1 = api.get("/api/ml/approvals?limit=1&offset=0").json()
        p2 = api.get("/api/ml/approvals?limit=1&offset=1").json()
        assert p1["total"] == 2 and len(p1["approvals"]) == len(p2["approvals"]) == 1
        assert p1["approvals"][0]["approval_id"] != p2["approvals"][0]["approval_id"]
        rejected = api.get("/api/ml/approvals?decision=rejected").json()
        assert rejected["total"] == 1 and rejected["approvals"][0]["model_id"] == other.model_id
        assert rejected["approvals"][0]["reason"] == "not good enough"
        assert api.get("/api/ml/approvals?decision=maybe").status_code == 422
        assert api.get("/api/ml/approvals?limit=201").status_code == 422

    def test_timeline_pagination_sources_and_since(self, db, api):
        for i in range(14):
            j = _job(db, version=f"t{i}")
            j.status, j.attempt_count = "running", 1
            db.commit()
        pages = [api.get(f"/api/ml/monitoring/timeline?limit=10&offset={o}").json() for o in (0, 10, 20)]
        items = [i for p in pages for i in p["items"]]
        assert len(items) == 28 and len({(i["source"], i["id"]) for i in items}) == 28
        assert [i["at"] for i in items] == sorted((i["at"] for i in items), reverse=True)
        assert pages[0]["has_more"] and pages[1]["has_more"] and not pages[2]["has_more"]
        only = api.get("/api/ml/monitoring/timeline?source=deployment").json()
        assert only["items"] == []
        future = (NOW() + timedelta(hours=1)).isoformat()
        assert api.get("/api/ml/monitoring/timeline", params={"since": future}).json()["items"] == []
        assert api.get("/api/ml/monitoring/timeline?since=yesterday").status_code == 422
        assert api.get("/api/ml/monitoring/timeline?source=disk").status_code == 422
        assert api.get("/api/ml/monitoring/timeline?limit=201").status_code == 422


# ---------------------------------------------------------------------------
# Read-only guarantees (normal, concurrent, failing, stuck-deployment conditions)
# ---------------------------------------------------------------------------

class TestReadOnly:
    def _hit_all(self, api, job_id=None):
        urls = ["/api/ml/monitoring/summary", "/api/ml/monitoring/timeline", "/api/ml/monitoring/timeline?offset=10",
                "/api/ml/jobs", "/api/ml/jobs?limit=2&status=completed", "/api/ml/evaluations?limit=5",
                "/api/ml/deployments?limit=5", "/api/ml/approvals?limit=5&decision=approved"]
        if job_id:
            urls.append(f"/api/ml/jobs/{job_id}")
        for u in urls:
            assert api.get(u).status_code == 200, u

    def test_monitoring_gets_change_nothing(self, db, Session, cand, deploy_env, api):
        mv, _ = cand
        _approve(db, Session, mv)
        mds.activate_model_version(db, mv.model_id, ADMIN)
        before = _table_state(db, deploy_env.serving)
        for _ in range(5):
            self._hit_all(api, mv.job_id)
        assert _table_state(db, deploy_env.serving) == before

    def test_concurrent_monitoring_during_activation_is_read_only(self, db, Session, cand, deploy_env):
        mv, data = cand
        _approve(db, Session, mv)
        entered, release = threading.Event(), threading.Event()
        deploy_env.warm_hook = lambda d: (entered.set(), release.wait(20))
        result = {}

        def activate():
            s = Session()                                                   # closed: an open PG transaction
            try:                                                            # would block the next test's DROP
                result.update(r=mds.activate_model_version(s, mv.model_id, ADMIN))
            finally:
                s.close()

        t = threading.Thread(target=activate)
        t.start()
        assert entered.wait(20)
        states, errors = [], []

        def poll():
            s = Session()
            try:
                for _ in range(3):
                    states.append(mon.summary(s)["deployment"]["consistency"]["state"])
            except Exception as exc:                                         # sqlite: busy writer
                errors.append(type(exc).__name__)
            finally:
                s.close()

        before = _table_state(db, deploy_env.serving)
        pollers = [threading.Thread(target=poll) for _ in range(4)]
        for p in pollers:
            p.start()
        for p in pollers:
            p.join(60)
        assert _table_state(db, deploy_env.serving) == before                # nothing written mid-deployment
        release.set()
        t.join(30)
        assert result["r"]["result"] == "activated"
        assert states and set(states) == {"in_progress"} and not errors

    def test_failure_returns_503_without_writes(self, db, deploy_env, api, monkeypatch):
        before = _table_state(db, deploy_env.serving)

        def broken(*a, **k):
            raise RuntimeError(r"db exploded at C:\secret")

        monkeypatch.setattr(mds, "deployment_overview", broken)
        r = api.get("/api/ml/monitoring/summary")
        assert r.status_code == 503 and "secret" not in r.text
        assert _table_state(db, deploy_env.serving) == before
        assert db.execute(text("SELECT 1")).scalar() == 1                    # session left usable

    def test_summary_never_runs_recovery(self, db, Session, cand, deploy_env, api):
        from test_a4_model_deployment import SimulatedCrash
        mv, data = cand
        _approve(db, Session, mv)
        deploy_env.warm_hook = lambda d: (_ for _ in ()).throw(SimulatedCrash())
        with pytest.raises(SimulatedCrash):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        deploy_env.warm_hook = None
        db.rollback()
        from app.models.training import ModelDeployment
        dep = db.query(ModelDeployment).one()
        dep.lease_expires_at = NOW() - timedelta(minutes=5)
        db.commit()
        alerts = _codes(api.get("/api/ml/monitoring/summary").json()["alerts"])
        assert "DEPLOYMENT_STUCK" in alerts
        db.expire_all()
        assert db.query(ModelDeployment).one().status == "activating"          # recovery is not a GET side effect
        assert deploy_env.serving.read_bytes() == data


# ---------------------------------------------------------------------------
# Real-JWT access control (isolated *test* database only)
# ---------------------------------------------------------------------------

_A5_ENDPOINTS = [
    "/api/ml/monitoring/summary",
    "/api/ml/monitoring/timeline",
    "/api/ml/monitoring/timeline?source=training&limit=5",
    "/api/ml/jobs?limit=5&status=failed",
    "/api/ml/jobs/some-job",
    "/api/ml/evaluations?limit=5",
    "/api/ml/approvals?limit=5",
    "/api/ml/deployments?limit=5",
]


@pytest.mark.skipif(
    "test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
    reason="real-JWT access test only runs against an isolated *test* database",
)
class TestAccessControl:
    @pytest.mark.parametrize("url", _A5_ENDPOINTS)
    def test_unauthenticated_and_normal_users_rejected(self, client, user_auth, url):
        assert client.get(url).status_code == 401
        assert client.get(url, headers=user_auth["headers"]).status_code == 403

    def test_real_admin_token_is_accepted(self, client, admin_auth, monitoring_env):
        r = client.get("/api/ml/monitoring/summary", headers=admin_auth["headers"])
        assert r.status_code == 200 and "alerts" in r.json()
        assert client.get("/api/ml/monitoring/timeline?limit=5", headers=admin_auth["headers"]).status_code == 200
