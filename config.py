"""
config.py — Construction Intelligence Agent settings.

Loads all configuration from environment variables / .env file.
Uses pydantic-settings for validation and type coercion.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── OpenAI ────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_input_cost_per_million: float = 0.40
    openai_output_cost_per_million: float = 1.60
    claude_model: str = ""

    # ── MongoDB API ───────────────────────────────────────
    api_base_url: str = "https://mongo.ifieldsmart.com"
    summary_by_trade_path: str = "/api/drawingText/summaryByTrade"
    summary_by_trade_and_set_path: str = "/api/drawingText/summaryByTradeAndSet"
    by_trade_path: str = "/api/drawingText/byTrade"
    by_trade_and_set_path: str = "/api/drawingText/byTradeAndSet"
    api_auth_token: str = ""
    api_timeout_seconds: int = 30

    # ── Pagination ────────────────────────────────────────
    api_page_size: int = 500
    max_pagination_pages: int = 200
    max_summary_records: int = 0
    parallel_fetch_concurrency: int = 10

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── App ───────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8003
    app_env: str = "production"

    # ── Token budgets ─────────────────────────────────────
    max_context_tokens: int = 120000
    max_output_tokens: int = 10000
    intent_max_tokens: int = 500
    follow_up_max_tokens: int = 400
    follow_up_questions_count: int = 3
    follow_up_questions_enabled: bool = True

    # ── Context compression ───────────────────────────────
    note_max_chars: int = 300
    note_dedup_prefix_chars: int = 50

    # ── Cache TTLs ────────────────────────────────────────
    cache_ttl_summary_data: int = 300
    cache_ttl_query: int = 3600

    # ── Session ───────────────────────────────────────────
    session_max_messages: int = 20
    session_ttl: int = 86400

    # ── Hallucination guard ───────────────────────────────
    hallucination_confidence_threshold: float = 0.70

    # ── Document storage ──────────────────────────────────
    docs_dir: str = "./generated_docs"
    docs_base_url: str = "https://ai.ifieldsmart.com/construction/api/documents"

    # ── Scalability ───────────────────────────────────────
    context_chunk_size: int = 500
    max_context_chars: int = 500000

    # ── SQL Server (project name lookup) ──────────────────
    sql_server_host: str = ""
    sql_server_port: int = 1433
    sql_database: str = "IFBIMIntegration_1"
    sql_username: str = ""
    sql_password: str = ""
    sql_driver: str = "ODBC Driver 18 for SQL Server"
    sql_connection_timeout: int = 10
    cache_ttl_project_name: int = 3600

    # ── S3 Storage (Phase 7) ─────────────────────────────
    storage_backend: str = "s3"
    s3_bucket_name: str = "agentic-ai-production"
    s3_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_agent_prefix: str = "construction-intelligence-agent"

    # ── Scope Gap Pipeline (Phase 11) ────────────────────
    scope_gap_model: str = "gpt-4.1"
    scope_gap_max_concurrent_jobs: int = 3
    scope_gap_completeness_threshold: float = 95.0
    scope_gap_max_attempts: int = 3
    scope_gap_record_threshold: int = 2000
    scope_gap_extraction_max_tokens: int = 8000
    scope_gap_classification_max_tokens: int = 4000
    scope_gap_quality_max_tokens: int = 4000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
