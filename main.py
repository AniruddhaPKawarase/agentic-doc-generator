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

from dotenv import load_dotenv
load_dotenv()  # Export .env values to os.environ (required by s3_utils)

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
from scope_pipeline.routers.scope_gap import router as scope_gap_router
from scope_pipeline.routers.status import router as status_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()
__version__ = "2.1.0"


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

    # ── S3 connectivity check (diagnostic) ───────────────────────
    if settings.storage_backend == "s3":
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from s3_utils.client import get_s3_client
            from s3_utils.config import get_s3_config
            s3_cfg = get_s3_config()
            s3_client = get_s3_client()
            if s3_client:
                logger.info(
                    "S3 READY: bucket=%s, prefix=%s, region=%s",
                    s3_cfg.bucket_name, s3_cfg.agent_prefix, s3_cfg.region,
                )
            else:
                logger.error(
                    "S3 CLIENT FAILED — documents will NOT upload. "
                    "STORAGE_BACKEND=%s, bucket=%s, has_creds=%s",
                    s3_cfg.storage_backend, s3_cfg.bucket_name, s3_cfg.has_credentials,
                )
        except Exception as e:
            logger.error("S3 startup check failed: %s", e)
    else:
        logger.info("Storage backend: local (S3 disabled)")

    # ── Scope Gap Pipeline (Phase 11) ─────────────────────────
    from scope_pipeline.config import get_pipeline_config
    from scope_pipeline.agents.extraction_agent import ExtractionAgent
    from scope_pipeline.agents.classification_agent import ClassificationAgent
    from scope_pipeline.agents.ambiguity_agent import AmbiguityAgent
    from scope_pipeline.agents.gotcha_agent import GotchaAgent
    from scope_pipeline.agents.completeness_agent import CompletenessAgent
    from scope_pipeline.agents.quality_agent import QualityAgent
    from scope_pipeline.services.document_agent import DocumentAgent as ScopeDocAgent
    from scope_pipeline.services.session_manager import ScopeGapSessionManager
    from scope_pipeline.services.job_manager import JobManager
    from scope_pipeline.services.chat_handler import ScopeGapChatHandler
    from scope_pipeline.services.data_fetcher import DataFetcher
    from scope_pipeline.orchestrator import ScopeGapPipeline

    pcfg = get_pipeline_config()
    scope_session_mgr = ScopeGapSessionManager(cache_service=cache)
    scope_data_fetcher = DataFetcher(api_client=api_client)
    scope_pipe = ScopeGapPipeline(
        extraction_agent=ExtractionAgent(
            api_key=pcfg.openai_api_key, model=pcfg.model,
            max_tokens=pcfg.extraction_max_tokens,
        ),
        classification_agent=ClassificationAgent(
            api_key=pcfg.openai_api_key, model=pcfg.model,
            max_tokens=pcfg.classification_max_tokens,
        ),
        ambiguity_agent=AmbiguityAgent(
            api_key=pcfg.openai_api_key, model=pcfg.model,
        ),
        gotcha_agent=GotchaAgent(
            api_key=pcfg.openai_api_key, model=pcfg.model,
        ),
        completeness_agent=CompletenessAgent(),
        quality_agent=QualityAgent(
            api_key=pcfg.openai_api_key, model=pcfg.model,
            max_tokens=pcfg.quality_max_tokens,
        ),
        document_agent=ScopeDocAgent(docs_dir=pcfg.docs_dir),
        data_fetcher=scope_data_fetcher,
        session_manager=scope_session_mgr,
        config=pcfg,
        sql_service=sql_service,
    )
    app.state.scope_pipeline = scope_pipe
    app.state.scope_job_manager = JobManager(
        pipeline=scope_pipe, max_concurrent=pcfg.max_concurrent_jobs,
    )
    app.state.scope_session_manager = scope_session_mgr
    app.state.scope_chat_handler = ScopeGapChatHandler(
        api_key=pcfg.openai_api_key, model=pcfg.model,
    )
    logger.info(
        "Scope Gap Pipeline initialized (model=%s, threshold=%.0f%%)",
        pcfg.model, pcfg.completeness_threshold,
    )

    # ── Phase 12 Services ─────────────────────────────────────────
    from scope_pipeline.services.project_session_manager import ProjectSessionManager
    from scope_pipeline.services.trade_color_service import TradeColorService
    from scope_pipeline.services.trade_discovery_service import TradeDiscoveryService
    from scope_pipeline.services.drawing_index_service import DrawingIndexService
    from scope_pipeline.services.export_service import ExportService
    from scope_pipeline.services.highlight_service import HighlightService
    from scope_pipeline.services.webhook_handler import WebhookHandler
    from scope_pipeline.project_orchestrator import ProjectOrchestrator

    project_session_mgr = ProjectSessionManager(cache_service=cache)
    trade_color_svc = TradeColorService()
    trade_discovery_svc = TradeDiscoveryService(api_client=api_client, cache_service=cache)
    drawing_index_svc = DrawingIndexService()
    export_svc = ExportService(docs_dir=pcfg.docs_dir)
    from scope_pipeline.services.async_s3_ops import AsyncS3Ops
    s3_bucket_name = ""
    s3_agent_prefix = ""
    if settings.storage_backend == "s3":
        try:
            from s3_utils.config import get_s3_config as _get_s3_cfg
            _s3c = _get_s3_cfg()
            s3_bucket_name = _s3c.bucket_name
            s3_agent_prefix = _s3c.agent_prefix
        except Exception:
            pass
    async_s3 = AsyncS3Ops(bucket_name=s3_bucket_name, prefix=s3_agent_prefix)
    highlight_svc = HighlightService(s3_ops=async_s3, cache_service=cache, s3_prefix=pcfg.highlight_s3_prefix)
    webhook_handler = WebhookHandler(
        secret=pcfg.webhook_secret,
        cache_service=cache,
        timestamp_tolerance=pcfg.webhook_timestamp_tolerance,
        idempotency_ttl=pcfg.webhook_idempotency_ttl,
    )
    project_orchestrator = ProjectOrchestrator(
        pipeline=scope_pipe,
        session_manager=project_session_mgr,
        trade_discovery=trade_discovery_svc,
        color_service=trade_color_svc,
        trade_concurrency=pcfg.trade_concurrency,
        result_freshness_ttl=pcfg.result_freshness_ttl,
        trade_pipeline_timeout=pcfg.trade_pipeline_timeout,
    )

    app.state.project_session_manager = project_session_mgr
    app.state.trade_color_service = trade_color_svc
    app.state.trade_discovery_service = trade_discovery_svc
    app.state.drawing_index_service = drawing_index_svc
    app.state.highlight_service = highlight_svc
    app.state.webhook_handler = webhook_handler
    app.state.export_service = export_svc
    app.state.project_orchestrator = project_orchestrator
    app.state.scope_data_fetcher = scope_data_fetcher

    logger.info("Phase 12 services initialized (trade_concurrency=%d)", pcfg.trade_concurrency)

    logger.info("All services initialised — API ready")

    yield  # App runs here

    # ── Shutdown ──────────────────────────────────────────────────
    logger.info("Shutting down — closing connections")
    await sql_service.close()
    await api_client.disconnect()
    await cache.disconnect()
    # Cancel any running background tasks
    import asyncio
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if tasks:
        logger.info("Cancelling %d background tasks", len(tasks))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Shutdown complete")


# ── FastAPI app ───────────────────────────────────────────────────

app = FastAPI(
    title="Construction Intelligence Agent",
    description=(
        "AI-powered construction document generation from MongoDB drawing data. "
        "Supports scopes, exhibits, reports, takeoffs, and specifications."
    ),
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the frontend origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from middleware.request_id import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)

# Auth middleware removed — will be added later
# from middleware.auth import BearerAuthMiddleware
# app.add_middleware(BearerAuthMiddleware)

# Rate limiting / concurrency cap removed — caused async event loop issues
# from middleware.rate_limit import setup_rate_limiting
# setup_rate_limiting(app)

# ── Routers ───────────────────────────────────────────────────────
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(projects_router)
app.include_router(scope_gap_router)
app.include_router(status_router)

from scope_pipeline.routers.project_endpoints import router as project_router
from scope_pipeline.routers.highlight_endpoints import router as highlight_router
from scope_pipeline.routers.webhook_endpoints import router as webhook_router

app.include_router(project_router)
app.include_router(highlight_router)
app.include_router(webhook_router)

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
        version=__version__,
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
