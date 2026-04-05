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


def get_pipeline_config() -> PipelineConfig:
    """Build pipeline config from environment + main settings."""
    import os
    s = get_settings()
    return PipelineConfig(
        model=os.getenv("SCOPE_GAP_MODEL", "gpt-4.1"),
        extraction_max_tokens=int(os.getenv("SCOPE_GAP_EXTRACTION_MAX_TOKENS", "8000")),
        classification_max_tokens=int(os.getenv("SCOPE_GAP_CLASSIFICATION_MAX_TOKENS", "4000")),
        quality_max_tokens=int(os.getenv("SCOPE_GAP_QUALITY_MAX_TOKENS", "4000")),
        max_attempts=int(os.getenv("SCOPE_GAP_MAX_ATTEMPTS", "3")),
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
    )
