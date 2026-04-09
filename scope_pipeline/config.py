"""
scope_pipeline/config.py — Pipeline-specific settings.

Reads from the main Settings class and provides pipeline-specific defaults.
"""

from dataclasses import dataclass
from config import get_settings


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline configuration."""
    model: str
    extraction_max_tokens: int
    classification_max_tokens: int
    quality_max_tokens: int
    max_attempts: int
    completeness_threshold: float
    record_threshold: int
    max_concurrent_jobs: int
    openai_api_key: str
    max_context_tokens: int
    storage_backend: str
    s3_bucket_name: str
    s3_region: str
    s3_agent_prefix: str
    docs_dir: str

    # Project Orchestrator
    trade_concurrency: int
    trade_concurrency_min: int
    result_freshness_ttl: int
    max_trades_per_project: int
    project_pipeline_timeout: int
    trade_pipeline_timeout: int
    adaptive_throttle_cooldown: int

    # Webhook
    webhook_secret: str
    webhook_allowed_ips: str
    webhook_timestamp_tolerance: int
    webhook_idempotency_ttl: int

    # Pre-computation
    precompute_priority: str
    precompute_concurrency: int
    precompute_enabled: bool

    # Highlights
    highlight_s3_prefix: str
    highlight_cache_ttl: int
    highlight_max_per_drawing: int
    highlight_max_per_project: int

    # Session
    session_max_versions_per_trade: int
    session_archive_after_days: int
    session_redis_ttl: int
    session_l1_max_trades: int


def get_pipeline_config() -> PipelineConfig:
    """Build pipeline config from environment + main settings."""
    import os
    s = get_settings()
    return PipelineConfig(
        model=os.getenv("SCOPE_GAP_MODEL", "gpt-4.1"),
        extraction_max_tokens=int(os.getenv("SCOPE_GAP_EXTRACTION_MAX_TOKENS", "8000")),
        classification_max_tokens=int(os.getenv("SCOPE_GAP_CLASSIFICATION_MAX_TOKENS", "4000")),
        quality_max_tokens=int(os.getenv("SCOPE_GAP_QUALITY_MAX_TOKENS", "4000")),
        max_attempts=int(os.getenv("SCOPE_GAP_MAX_ATTEMPTS", "5")),
        completeness_threshold=float(os.getenv("SCOPE_GAP_COMPLETENESS_THRESHOLD", "95.0")),
        record_threshold=int(os.getenv("SCOPE_GAP_RECORD_THRESHOLD", "2000")),
        max_concurrent_jobs=int(os.getenv("SCOPE_GAP_MAX_CONCURRENT_JOBS", "3")),
        openai_api_key=s.openai_api_key,
        max_context_tokens=s.max_context_tokens,
        storage_backend=s.storage_backend,
        s3_bucket_name=s.s3_bucket_name,
        s3_region=s.s3_region,
        s3_agent_prefix=s.s3_agent_prefix,
        docs_dir=s.docs_dir,
        # Project Orchestrator
        trade_concurrency=int(os.getenv("TRADE_CONCURRENCY", "10")),
        trade_concurrency_min=int(os.getenv("TRADE_CONCURRENCY_MIN", "4")),
        result_freshness_ttl=int(os.getenv("RESULT_FRESHNESS_TTL", "86400")),
        max_trades_per_project=int(os.getenv("MAX_TRADES_PER_PROJECT", "200")),
        project_pipeline_timeout=int(os.getenv("PROJECT_PIPELINE_TIMEOUT", "7200")),
        trade_pipeline_timeout=int(os.getenv("TRADE_PIPELINE_TIMEOUT", "600")),
        adaptive_throttle_cooldown=int(os.getenv("ADAPTIVE_THROTTLE_COOLDOWN", "60")),
        # Webhook
        webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        webhook_allowed_ips=os.getenv("WEBHOOK_ALLOWED_IPS", ""),
        webhook_timestamp_tolerance=int(os.getenv("WEBHOOK_TIMESTAMP_TOLERANCE", "300")),
        webhook_idempotency_ttl=int(os.getenv("WEBHOOK_IDEMPOTENCY_TTL", "3600")),
        # Pre-computation
        precompute_priority=os.getenv("PRECOMPUTE_PRIORITY", "low"),
        precompute_concurrency=int(os.getenv("PRECOMPUTE_CONCURRENCY", "5")),
        precompute_enabled=os.getenv("PRECOMPUTE_ENABLED", "true").lower() == "true",
        # Highlights
        highlight_s3_prefix=os.getenv("HIGHLIGHT_S3_PREFIX", "highlights"),
        highlight_cache_ttl=int(os.getenv("HIGHLIGHT_CACHE_TTL", "300")),
        highlight_max_per_drawing=int(os.getenv("HIGHLIGHT_MAX_PER_DRAWING", "500")),
        highlight_max_per_project=int(os.getenv("HIGHLIGHT_MAX_PER_PROJECT", "10000")),
        # Session
        session_max_versions_per_trade=int(os.getenv("SESSION_MAX_VERSIONS_PER_TRADE", "5")),
        session_archive_after_days=int(os.getenv("SESSION_ARCHIVE_AFTER_DAYS", "30")),
        session_redis_ttl=int(os.getenv("SESSION_REDIS_TTL", "604800")),
        session_l1_max_trades=int(os.getenv("SESSION_L1_MAX_TRADES", "20")),
    )
