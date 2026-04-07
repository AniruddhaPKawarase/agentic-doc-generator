"""
models/error_codes.py — Structured error codes for API responses.
"""


class ErrorCode:
    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"
    DATA_FETCH_FAILED = "DATA_FETCH_FAILED"
    LLM_ERROR = "LLM_ERROR"
    DOCUMENT_GENERATION_FAILED = "DOCUMENT_GENERATION_FAILED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_FAILED = "AUTH_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_OVERLOADED = "SERVER_OVERLOADED"


def error_response(code: str, detail: str) -> dict:
    """Build a structured error response."""
    return {"error": detail, "error_code": code}
