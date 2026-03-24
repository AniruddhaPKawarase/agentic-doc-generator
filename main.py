"""
main.py  —  FastAPI application entry point.

Startup sequence:
  1. Load settings from .env
  2. Connect Redis (graceful fallback to in-memory)
  3. Connect HTTP client for MongoDB APIs
  4. Wire all services and agents onto app.state
  5. Register routers

Shutdown sequence:
  1. Disconnect Redis
  2. Close HTTP client
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings
from models.schemas import HealthResponse

# Services
from services.api_client import APIClient
from services.cache_service import CacheService
from services.context_builder import ContextBuilder
from services.document_generator import DocumentGenerator
from services.hallucination_guard import HallucinationGuard
from services.session_service import SessionService
from services.sql_service import SQLService
from services.token_tracker import TokenTracker

# Agents
from agents.data_agent import DataAgent
from agents.generation_agent import GenerationAgent
from agents.intent_agent import IntentAgent

# Routers
from routers.chat import router as chat_router
from routers.documents import router as documents_router
from routers.projects import router as projects_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle manager."""
    logger.info("=" * 60)
    logger.info(" Construction Intelligence Agent — Starting up")
    logger.info("=" * 60)

    # ── Init services ─────────────────────────────────────────────
    cache = CacheService(redis_url=settings.redis_url)
    await cache.connect()

    api_client = APIClient(cache=cache)
    await api_client.connect()

    session_service = SessionService(
        cache=cache,
        max_messages=settings.session_max_messages,
        session_ttl=settings.session_ttl,
    )
    token_tracker = TokenTracker(cache=cache)
    document_generator = DocumentGenerator()
    hallucination_guard = HallucinationGuard(
        confidence_threshold=settings.hallucination_confidence_threshold
    )

    # SQL service — project name lookup (v3)
    # Graceful: startup never fails even if SQL is unreachable or pyodbc is missing.
    sql_service = SQLService(cache=cache)
    if settings.sql_server_host:
        logger.info(
            "SQL project name service configured: host=%s db=%s",
            settings.sql_server_host, settings.sql_database,
        )
    else:
        logger.warning(
            "SQL_SERVER_HOST not set — project name lookup disabled (will fall back to project ID)"
        )

    # ── Init agents ───────────────────────────────────────────────
    intent_agent = IntentAgent()
    data_agent = DataAgent(api_client=api_client, cache=cache)
    generation_agent = GenerationAgent(
        intent_agent=intent_agent,
        data_agent=data_agent,
        session_service=session_service,
        token_tracker=token_tracker,
        cache=cache,
        document_generator=document_generator,
        hallucination_guard=hallucination_guard,
        sql_service=sql_service,
    )

    # ── Attach to app.state (dependency injection) ────────────────
    app.state.cache = cache
    app.state.api_client = api_client
    app.state.session_service = session_service
    app.state.token_tracker = token_tracker
    app.state.generation_agent = generation_agent

    logger.info("All services initialised — API ready")

    yield  # App runs here

    # ── Shutdown ──────────────────────────────────────────────────
    logger.info("Shutting down...")
    await sql_service.close()
    await api_client.disconnect()
    await cache.disconnect()
    logger.info("Shutdown complete")


# ── FastAPI app ───────────────────────────────────────────────────

app = FastAPI(
    title="Construction Intelligence Agent",
    description=(
        "AI-powered construction document generation from MongoDB drawing data. "
        "Supports scopes, exhibits, reports, takeoffs, and specifications."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(projects_router)

# ── Static files (frontend) ───────────────────────────────────────
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# ── Root routes ───────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_frontend():
    index = frontend_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"message": "Construction Intelligence Agent API", "docs": "/docs"})


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check():
    """System health check."""
    redis_status = await app.state.cache.status()
    openai_status = "configured" if settings.openai_api_key else "not configured"
    return HealthResponse(
        status="ok",
        redis=redis_status,
        openai=openai_status,
    )


# ── Dev entrypoint ────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level="info",
    )
