import json
import logging
import uuid
import pytest
from app.logging_config import request_id_var, user_id_var, StructuredJSONFormatter
from app.dependencies.auth import create_access_token

class LogCaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

@pytest.fixture
def capture_logs():
    logger = logging.getLogger("test_logger")
    handler = LogCaptureHandler()
    formatter = StructuredJSONFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    yield logger, handler
    
    logger.removeHandler(handler)

def test_request_id_in_response_header(client):
    r = client.get("/api/dataset/health")
    assert r.status_code == 200
    assert "X-Request-ID" in r.headers
    val = r.headers["X-Request-ID"]
    uuid.UUID(val)

def test_request_id_propagation_to_header(client):
    req_id = str(uuid.uuid4())
    r = client.get("/api/dataset/health", headers={"X-Request-ID": req_id})
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == req_id

def test_json_formatter_fields(capture_logs):
    logger, handler = capture_logs
    
    req_token = request_id_var.set("test-req-id")
    user_token = user_id_var.set("test-user-id")
    
    try:
        logger.info("Test message", extra={"additional_key": "some-value"})
        
        assert len(handler.records) == 1
        record = handler.records[0]
        
        formatter = StructuredJSONFormatter()
        json_output = formatter.format(record)
        
        data = json.loads(json_output)
        assert data["message"] == "Test message"
        assert data["request_id"] == "test-req-id"
        assert data["user_id"] == "test-user-id"
        assert data["additional_key"] == "some-value"
        assert "timestamp" in data
        assert data["level"] == "INFO"
        assert data["module"] == "test_logger"
    finally:
        request_id_var.reset(req_token)
        user_id_var.reset(user_token)

def test_logging_redaction(capture_logs):
    logger, handler = capture_logs
    formatter = StructuredJSONFormatter()
    
    # Test dictionary key redaction
    logger.info("User login", extra={"password": "SecretPassword123", "jwt_token": "secret-jwt"})
    record = handler.records[0]
    data = json.loads(formatter.format(record))
    assert data["password"] == "[REDACTED]"
    assert data["jwt_token"] == "[REDACTED]"
    
    # Test message content redaction
    logger.info("Saving jwt token to file")
    record = handler.records[1]
    data = json.loads(formatter.format(record))
    assert data["message"] == "[REDACTED MESSAGE CONTAINS SENSITIVE DATA]"
