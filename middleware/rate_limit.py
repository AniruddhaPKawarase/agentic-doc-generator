"""
middleware/rate_limit.py — slowapi rate limiting + concurrency cap.
"""
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from config import get_settings

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)


class ConcurrencyLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_concurrent: int = 50):
        super().__init__(app)
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def dispatch(self, request: Request, call_next):
        if not self._semaphore._value:
            return JSONResponse(
                status_code=503,
                content={"error": "Server at capacity. Please retry shortly."},
            )
        async with self._semaphore:
            return await call_next(request)


def setup_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_middleware(
        ConcurrencyLimitMiddleware,
        max_concurrent=settings.max_concurrent_requests,
    )
