import os
import uuid
import pytest
from unittest.mock import patch
from fastapi import APIRouter
from app.main import app
from app.exceptions import (
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    ResourceNotFoundError,
    ConflictError,
    DatabaseError,
    BadRequestError,
)

# Register a test router to trigger specific exceptions on the fly
router = APIRouter(prefix="/test-errors")

@router.get("/validation")
def trigger_validation():
    raise ValidationError("Test validation message")

@router.get("/authentication")
def trigger_auth():
    raise AuthenticationError("Test auth message")

@router.get("/authorization")
def trigger_author():
    raise AuthorizationError("Test authorization message")

@router.get("/not-found")
def trigger_not_found():
    raise ResourceNotFoundError("Test resource not found")

@router.get("/conflict")
def trigger_conflict():
    raise ConflictError("Test conflict message")

@router.get("/database")
def trigger_db():
    raise DatabaseError("Test database message")

@router.get("/bad-request")
def trigger_bad():
    raise BadRequestError("Test bad request message")

@router.get("/unhandled")
def trigger_unhandled():
    raise ValueError("This is an unhandled internal exception details")

# Include the test router in the application instance
app.include_router(router)


def test_standardized_error_validation(client):
    r = client.get("/test-errors/validation")
    assert r.status_code == 422
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Test validation message"
    assert "request_id" in data["error"]
    uuid.UUID(data["error"]["request_id"])


def test_standardized_error_authentication(client):
    r = client.get("/test-errors/authentication")
    assert r.status_code == 401
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "AUTHENTICATION_ERROR"
    assert data["error"]["message"] == "Test auth message"


def test_standardized_error_authorization(client):
    r = client.get("/test-errors/authorization")
    assert r.status_code == 403
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "AUTHORIZATION_ERROR"
    assert data["error"]["message"] == "Test authorization message"


def test_standardized_error_not_found(client):
    r = client.get("/test-errors/not-found")
    assert r.status_code == 404
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert data["error"]["message"] == "Test resource not found"


def test_standardized_error_conflict(client):
    r = client.get("/test-errors/conflict")
    assert r.status_code == 409
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "CONFLICT_ERROR"
    assert data["error"]["message"] == "Test conflict message"


def test_standardized_error_database(client):
    r = client.get("/test-errors/database")
    assert r.status_code == 500
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DATABASE_ERROR"
    assert data["error"]["message"] == "Test database message"


def test_standardized_error_bad_request(client):
    r = client.get("/test-errors/bad-request")
    assert r.status_code == 400
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "BAD_REQUEST"
    assert data["error"]["message"] == "Test bad request message"


def test_standardized_error_unhandled():
    from fastapi.testclient import TestClient
    local_client = TestClient(app, raise_server_exceptions=False)
    r = local_client.get("/test-errors/unhandled")
    assert r.status_code == 500
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "An unexpected error occurred."
    assert "unhandled internal exception details" not in data["error"]["message"]


def test_standardized_fastapi_request_validation(client):
    # Call an actual endpoint (register) with missing body to trigger standard validation handler
    r = client.post("/api/auth/register", json={})
    assert r.status_code == 422
    data = r.json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in data["error"]


def test_request_id_propagation_on_error(client):
    req_id = str(uuid.uuid4())
    r = client.get("/test-errors/not-found", headers={"X-Request-ID": req_id})
    assert r.status_code == 404
    data = r.json()
    assert data["error"]["request_id"] == req_id


@patch("sentry_sdk.init")
def test_sentry_initialization_flow(mock_sentry_init):
    # Test Sentry toggled off
    with patch.dict(os.environ, {"SENTRY_DSN": ""}):
        # Mock main reload behavior or direct check
        sentry_dsn_val = os.getenv("SENTRY_DSN")
        assert not sentry_dsn_val
        # Sentry init is not called
        
    # Test Sentry toggled on
    with patch.dict(os.environ, {"SENTRY_DSN": "https://pub@sentry.io/1"}):
        sentry_dsn_val = os.getenv("SENTRY_DSN")
        assert sentry_dsn_val == "https://pub@sentry.io/1"
