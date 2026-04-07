"""
middleware/auth.py — Bearer token authentication for /api/ routes.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from config import get_settings


class BearerAuthMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or path in self.SKIP_PATHS:
            return await call_next(request)

        settings = get_settings()
        expected_token = settings.api_auth_token
        if not expected_token:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"error": "Missing or invalid Authorization header"})

        if auth_header[7:] != expected_token:
            return JSONResponse(status_code=403, content={"error": "Invalid authentication token"})

        return await call_next(request)
