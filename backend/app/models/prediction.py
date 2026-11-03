"""
Immutable prediction provenance (ZWM v1.1.0, Block A6.1).

One PredictionRecord per AI inference request, written by the inference path
itself at the moment the result is produced. It pins exactly which model produced
the result -- the SHA-256 of the artifact the in-memory model was loaded from, and
the existing model version / deployment that artifact belongs to -- so later
activations or rollbacks never change what a past prediction is attributed to.

References to existing records (model_versions, model_deployments, images,
training_snapshots) are plain ids without foreign keys: evidence outlives rows.
Unavailable information is NULL, never inferred (e.g. a model whose artifact is not
a recorded deployment has model_version_id = NULL and attribution
'unmanaged_artifact'). Corrections belong to a separate, future feedback workflow.

Rows are append-only: the ORM refuses updates/deletes and, on PostgreSQL, a trigger
refuses UPDATE/DELETE whatever the code path.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DDL, DateTime, Index, Integer, String, Text, event

from app.database import Base

# source of the inference request
SOURCE_ML_PREDICT = "ml_predict"                    # POST /api/ml/predict
SOURCE_UPLOAD_VALIDATION = "upload_validation"      # AI category check during image upload
SOURCE_AI_SEGMENT = "ai_segment"                    # POST /api/ai/segment
SOURCE_AI_POLYGON_CLICK = "ai_polygon_click"        # POST /api/ai/polygon-click

# which model family produced it
KIND_DEPLOYED_DETECTOR = "deployed_detector"        # the served YOLO_MODEL_PATH model (A4 deployments)
KIND_SEGMENTATION_ASSISTANT = "segmentation_assistant"   # AIDetector (bundled seg weights + OpenCV)

# how the model identity was established
ATTR_ACTIVE_DEPLOYMENT = "active_deployment"        # artifact SHA == the deployment active at inference
ATTR_HISTORICAL_DEPLOYMENT = "historical_deployment"     # artifact SHA == an earlier served deployment
ATTR_UNMANAGED = "unmanaged_artifact"               # artifact known by SHA, not a recorded deployment
ATTR_UNVERIFIED = "unverified"                      # identity could not be confirmed at inference
ATTR_NOT_APPLICABLE = "not_applicable"              # not a deployed model (segmentation assistant)

STATUS_SUCCEEDED, STATUS_NO_RESULT, STATUS_FAILED = "succeeded", "no_result", "failed"


class PredictionRecordImmutableError(Exception):
    pass


class PredictionRecord(Base):
    __tablename__ = "prediction_records"
    __table_args__ = (
        Index("ix_prediction_records_requested_by_created", "requested_by", "created_at"),
    )

    prediction_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                        index=True)
    source = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False)
    image_id = Column(String(36), nullable=True, index=True)          # NULL: no legitimate association
    requested_by = Column(String(36), nullable=True)
    environment = Column(String(32), nullable=False)                 # e.g. production | development | test

    # model identity at inference time
    model_kind = Column(String(32), nullable=False)
    attribution = Column(String(32), nullable=False)
    model_sha256 = Column(String(64), nullable=True)
    model_artifact = Column(String(255), nullable=True)               # file name only, never a path
    inference_backend = Column(String(16), nullable=True)             # pytorch | onnx | NULL
    inference_engine = Column(String(64), nullable=True)              # e.g. yolo_seg_mask | opencv_grabcut
    model_version_id = Column(String(36), nullable=True, index=True)  # existing model_versions.model_id
    model_version = Column(String(20), nullable=True)
    deployment_id = Column(String(36), nullable=True, index=True)     # existing model_deployments row
    snapshot_id = Column(Integer, nullable=True)                      # training snapshot of the model
    class_map_sha256 = Column(String(64), nullable=True)
    class_names = Column(JSON, nullable=True)                         # {index: name} the model reported

    # result
    detection_count = Column(Integer, nullable=False, default=0)
    detections = Column(JSON, nullable=False)                         # [{class_id,label,confidence,bbox,polygon}]
    confidence_is_model_score = Column(Boolean, nullable=False)
    result = Column(JSON, nullable=True)                              # structured result returned to the caller
    request_params = Column(JSON, nullable=True)
    error = Column(String(128), nullable=True)                        # error class only, never a trace


@event.listens_for(PredictionRecord, "before_update")
def _prediction_no_update(mapper, connection, target):
    raise PredictionRecordImmutableError("prediction records are immutable")


@event.listens_for(PredictionRecord, "before_delete")
def _prediction_no_delete(mapper, connection, target):
    raise PredictionRecordImmutableError("prediction records cannot be deleted")


PREDICTION_GUARD_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION zwm_guard_prediction_records() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'prediction records are append-only' USING ERRCODE = 'check_violation';
END
$$ LANGUAGE plpgsql
"""
PREDICTION_GUARD_TRIGGER_SQL = (
    "CREATE TRIGGER trg_prediction_records_append_only BEFORE UPDATE OR DELETE ON prediction_records "
    "FOR EACH ROW EXECUTE FUNCTION zwm_guard_prediction_records()"
)

event.listen(PredictionRecord.__table__, "after_create",
             DDL(PREDICTION_GUARD_FUNCTION_SQL).execute_if(dialect="postgresql"))
event.listen(PredictionRecord.__table__, "after_create",
             DDL(PREDICTION_GUARD_TRIGGER_SQL).execute_if(dialect="postgresql"))
