"""
Prediction provenance (ZWM v1.1.0, Block A6.1).

Attribution rule: a prediction is attributed to the artifact the in-memory model
object was loaded from (its SHA-256, captured together with the model by
YOLOModelCache.get_model_with_identity). That SHA is then matched against the A4
deployment records -- never "whichever model is active now". The lookup runs right
after the model is obtained and before inference, so a concurrent activation or
rollback cannot change the answer; and records are immutable afterwards.
"""
import hashlib
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.prediction import (
    ATTR_ACTIVE_DEPLOYMENT,
    ATTR_HISTORICAL_DEPLOYMENT,
    ATTR_NOT_APPLICABLE,
    ATTR_UNMANAGED,
    ATTR_UNVERIFIED,
    KIND_DEPLOYED_DETECTOR,
    KIND_SEGMENTATION_ASSISTANT,
    PredictionRecord,
)

MAX_PAGE = 200
_SERVED = ("active", "superseded", "rolled_back")


def environment_label() -> str:
    """'test' inside the isolated test harness (fs_safety test root), else APP_ENV."""
    from app.services.fs_safety import test_root
    return "test" if test_root() is not None else (settings.APP_ENV or "unknown")


def _class_map_sha(db: Session, snapshot_id: Optional[int]) -> Optional[str]:
    if snapshot_id is None:
        return None
    from app.models.training import TrainingSnapshot
    snap = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == snapshot_id).first()
    if snap is None or snap.class_map is None:
        return None
    return hashlib.sha256(json.dumps(snap.class_map, sort_keys=True, default=str).encode()).hexdigest()


def resolve_deployed_identity(db: Session, identity: Optional[dict]) -> dict:
    """
    Provenance fields for the deployed detector, from the identity captured with the
    model object. Unknown -> NULL fields and an explicit attribution, never a guess.
    """
    from app.models.training import ModelDeployment

    out = {"model_kind": KIND_DEPLOYED_DETECTOR, "attribution": ATTR_UNVERIFIED, "model_sha256": None,
           "model_artifact": None, "inference_backend": None, "model_version_id": None, "model_version": None,
           "deployment_id": None, "snapshot_id": None, "class_map_sha256": None}
    if not identity or not identity.get("sha256"):
        return out
    sha = identity["sha256"]
    out.update(model_sha256=sha, model_artifact=identity.get("artifact"),
               inference_backend=identity.get("backend"), attribution=ATTR_UNMANAGED)
    active = (db.query(ModelDeployment).filter(ModelDeployment.status == "active")
              .order_by(ModelDeployment.finished_at.desc()).first())
    dep = active if active is not None and active.weights_sha256 == sha else None
    if dep is not None:
        out["attribution"] = ATTR_ACTIVE_DEPLOYMENT
    else:
        dep = (db.query(ModelDeployment)
               .filter(ModelDeployment.weights_sha256 == sha, ModelDeployment.status.in_(_SERVED))
               .order_by(ModelDeployment.finished_at.desc(), ModelDeployment.deployment_id).first())
        if dep is not None:
            out["attribution"] = ATTR_HISTORICAL_DEPLOYMENT
    if dep is not None:
        out.update(deployment_id=dep.deployment_id, model_version_id=dep.model_id,
                   model_version=dep.model_version, snapshot_id=dep.snapshot_id,
                   class_map_sha256=_class_map_sha(db, dep.snapshot_id))
    return out


def segmentation_identity(detector) -> dict:
    ident = detector.model_identity() if hasattr(detector, "model_identity") else {"loaded": False}
    return {"model_kind": KIND_SEGMENTATION_ASSISTANT, "attribution": ATTR_NOT_APPLICABLE,
            "model_sha256": ident.get("sha256"), "model_artifact": ident.get("artifact"),
            "inference_backend": "pytorch" if ident.get("loaded") else None,
            "model_version_id": None, "model_version": None, "deployment_id": None,
            "snapshot_id": None, "class_map_sha256": None}


def class_names_of(model) -> Optional[dict]:
    names = getattr(model, "names", None)
    if isinstance(names, dict):
        return {str(k): str(v) for k, v in names.items()}
    if isinstance(names, (list, tuple)):
        return {str(i): str(v) for i, v in enumerate(names)}
    return None


def segmentation_detections(polygons: list) -> list:
    """
    AIDetector polygons. Its 'confidence' is a fixed constant per code path, not a
    model score: it is kept as reported_confidence and confidence stays NULL.
    """
    out = []
    for p in polygons or []:
        if not isinstance(p, dict):
            continue
        out.append({"class_id": None, "label": p.get("class_name"), "confidence": None,
                    "reported_confidence": p.get("confidence"), "bbox": p.get("bbox"),
                    "polygon": p.get("points"), "engine": p.get("engine")})
    return out


def new_record(*, source: str, status: str, identity: dict, detections: list, confidence_is_model_score: bool,
               image_id: Optional[str] = None, requested_by: Optional[str] = None,
               class_names: Optional[dict] = None, result=None, request_params=None,
               engine: Optional[str] = None, error: Optional[str] = None) -> PredictionRecord:
    """Build (not commit) one immutable prediction record."""
    return PredictionRecord(
        source=source, status=status, image_id=image_id, requested_by=requested_by,
        environment=environment_label(), inference_engine=engine, class_names=class_names,
        detection_count=len(detections or []), detections=detections or [],
        confidence_is_model_score=confidence_is_model_score, result=result,
        request_params=request_params, error=error, **identity,
    )


def to_dict(rec: PredictionRecord, include_requester: bool = False) -> dict:
    data = {
        "prediction_id": rec.prediction_id,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "source": rec.source, "status": rec.status, "image_id": rec.image_id, "environment": rec.environment,
        "model": {"kind": rec.model_kind, "attribution": rec.attribution, "sha256": rec.model_sha256,
                  "artifact": rec.model_artifact, "backend": rec.inference_backend, "engine": rec.inference_engine,
                  "model_version_id": rec.model_version_id, "model_version": rec.model_version,
                  "deployment_id": rec.deployment_id, "snapshot_id": rec.snapshot_id,
                  "class_map_sha256": rec.class_map_sha256, "class_names": rec.class_names},
        "detection_count": rec.detection_count, "detections": rec.detections,
        "confidence_is_model_score": rec.confidence_is_model_score,
        "request_params": rec.request_params, "error": rec.error,
    }
    if include_requester:
        data["requested_by"] = rec.requested_by
    return data


def list_predictions(db: Session, *, requested_by: Optional[str] = None, image_id: Optional[str] = None,
                     source: Optional[str] = None, status: Optional[str] = None, model_version_id: Optional[str] = None,
                     limit: int = 50, offset: int = 0, include_requester: bool = False) -> dict:
    q = db.query(PredictionRecord)
    if requested_by is not None:
        q = q.filter(PredictionRecord.requested_by == requested_by)
    if image_id:
        q = q.filter(PredictionRecord.image_id == image_id)
    if source:
        q = q.filter(PredictionRecord.source == source)
    if status:
        q = q.filter(PredictionRecord.status == status)
    if model_version_id:
        q = q.filter(PredictionRecord.model_version_id == model_version_id)
    total = q.count()
    rows = (q.order_by(PredictionRecord.created_at.desc(), PredictionRecord.prediction_id)
            .offset(offset).limit(min(limit, MAX_PAGE)).all())
    return {"items": [to_dict(r, include_requester) for r in rows], "total": total, "limit": limit, "offset": offset}
