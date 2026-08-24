import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.logging_config import request_id_var

logger = logging.getLogger("app.exceptions")

class ZWMException(Exception):
    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_SERVER_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)

class ValidationError(ZWMException):
    def __init__(self, message: str):
        super().__init__(message, status_code=422, error_code="VALIDATION_ERROR")

class AuthenticationError(ZWMException):
    def __init__(self, message: str):
        super().__init__(message, status_code=401, error_code="AUTHENTICATION_ERROR")

class AuthorizationError(ZWMException):
    def __init__(self, message: str):
        super().__init__(message, status_code=403, error_code="AUTHORIZATION_ERROR")

class ResourceNotFoundError(ZWMException):
    def __init__(self, message: str):
        super().__init__(message, status_code=404, error_code="RESOURCE_NOT_FOUND")

class ConflictError(ZWMException):
    def __init__(self, message: str):
        super().__init__(message, status_code=409, error_code="CONFLICT_ERROR")

class DatabaseError(ZWMException):
    def __init__(self, message: str):
        super().__init__(message, status_code=500, error_code="DATABASE_ERROR")

class BadRequestError(ZWMException):
    def __init__(self, message: str):
        super().__init__(message, status_code=400, error_code="BAD_REQUEST")

def get_request_id():
    return request_id_var.get() or "N/A"

async def zwm_exception_handler(request: Request, exc: ZWMException):
    req_id = get_request_id()
    logger.error(f"Application error: {exc.error_code} - {exc.message}", extra={"error_code": exc.error_code, "status_code": exc.status_code})
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "request_id": req_id
            }
        }
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = get_request_id()
    error_code = "INTERNAL_SERVER_ERROR"
    if exc.status_code == 400:
        error_code = "BAD_REQUEST"
    elif exc.status_code == 401:
        error_code = "AUTHENTICATION_ERROR"
    elif exc.status_code == 403:
        error_code = "AUTHORIZATION_ERROR"
    elif exc.status_code == 404:
        error_code = "RESOURCE_NOT_FOUND"
    elif exc.status_code == 409:
        error_code = "CONFLICT_ERROR"
    elif exc.status_code == 422:
        error_code = "VALIDATION_ERROR"
    elif exc.status_code == 429:
        error_code = "TOO_MANY_REQUESTS"
        
    logger.error(f"HTTP exception: {error_code} - {exc.detail}", extra={"error_code": error_code, "status_code": exc.status_code})
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": error_code,
                "message": exc.detail,
                "request_id": req_id
            }
        }
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = get_request_id()
    errors = []
    for err in exc.errors():
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Validation error")
        errors.append(f"{loc}: {msg}")
    message = "; ".join(errors) or "Validation failed"
    
    logger.error(f"Validation error: {message}", extra={"error_code": "VALIDATION_ERROR", "status_code": 422})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": message,
                "request_id": req_id
            }
        }
    )

async def unhandled_exception_handler(request: Request, exc: Exception):
    req_id = get_request_id()
    logger.exception(f"Unhandled exception: {str(exc)}", extra={"error_code": "INTERNAL_SERVER_ERROR", "status_code": 500})
    
    try:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass
        
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred.",
                "request_id": req_id
            }
        }
    )
