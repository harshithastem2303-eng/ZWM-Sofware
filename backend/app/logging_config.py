import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

request_id_var = contextvars.ContextVar("request_id", default=None)
user_id_var = contextvars.ContextVar("user_id", default=None)

class StructuredJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        
        req_id = request_id_var.get()
        if req_id:
            log_data["request_id"] = req_id
            
        usr_id = user_id_var.get()
        if usr_id:
            log_data["user_id"] = usr_id
            
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        for key, val in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "msg", "name", "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName"
            } and not key.startswith("_"):
                log_data[key] = val
                
        # Redact sensitive parameters
        for key in list(log_data.keys()):
            if any(k in key.lower() for k in ["password", "token", "jwt", "secret", "credentials", "authorization"]):
                log_data[key] = "[REDACTED]"
                
        # Redact sensitive message contents
        msg_str = str(log_data["message"]).lower()
        if any(k in msg_str for k in ["password", "token", "jwt", "secret"]):
            log_data["message"] = "[REDACTED MESSAGE CONTAINS SENSITIVE DATA]"
            
        return json.dumps(log_data)

def setup_logging():
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJSONFormatter())
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    
    # Silence verbose default loggers to prevent double log records
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
