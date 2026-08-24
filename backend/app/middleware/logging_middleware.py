import uuid
import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.logging_config import request_id_var, user_id_var

logger = logging.getLogger("app.middleware")

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate or extract X-Request-ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Set ContextVars
        req_token = request_id_var.set(request_id)
        user_token = user_id_var.set(None)
        
        start_time = time.perf_counter()
        
        # Log request start
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "endpoint": request.url.path,
                "query_params": str(request.query_params),
            }
        )
        
        try:
            response = await call_next(request)
            
            elapsed = (time.perf_counter() - start_time) * 1000.0  # in ms
            logger.info(
                f"Request finished: {request.method} {request.url.path} - Status: {response.status_code} - Duration: {elapsed:.2f}ms",
                extra={
                    "method": request.method,
                    "endpoint": request.url.path,
                    "status_code": response.status_code,
                    "response_time": f"{elapsed:.2f}ms",
                }
            )
            
            response.headers["X-Request-ID"] = request_id
            return response
            
        except Exception as exc:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            logger.exception(
                f"Request failed: {request.method} {request.url.path} - Exception: {str(exc)}",
                extra={
                    "method": request.method,
                    "endpoint": request.url.path,
                    "status_code": 500,
                    "response_time": f"{elapsed:.2f}ms",
                }
            )
            raise
            
        finally:
            request_id_var.reset(req_token)
            user_id_var.reset(user_token)
