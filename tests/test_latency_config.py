"""Tests for latency optimization config settings."""
import os
from unittest.mock import patch


def test_bulk_fetch_defaults():
    from config import Settings
    s = Settings(openai_api_key="test-key")
    assert s.bulk_fetch_enabled is True
    assert s.bulk_fetch_timeout == 60


def test_tiered_model_defaults():
    from config import Settings
    s = Settings(openai_api_key="test-key")
    assert s.intent_model == "gpt-4.1-nano"
    assert s.followup_model == "gpt-4.1-nano"


def test_disk_cache_defaults():
    from config import Settings
    s = Settings(openai_api_key="test-key")
    assert s.disk_cache_enabled is True
    assert s.disk_cache_dir == ".cache"
    assert s.cache_warmup_enabled is True


def test_updated_defaults():
    from config import Settings
    s = Settings(openai_api_key="test-key")
    assert s.max_output_tokens == 7000
    assert s.note_max_chars == 200
    assert s.api_timeout_seconds == 60
    assert s.cache_ttl_summary_data == 900
    assert s.parallel_fetch_concurrency == 50


def test_env_override_bulk_fetch():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "BULK_FETCH_ENABLED": "false",
        "BULK_FETCH_TIMEOUT": "120",
    }):
        from config import Settings
        s = Settings()
        assert s.bulk_fetch_enabled is False
        assert s.bulk_fetch_timeout == 120


def test_env_override_tiered_models():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "test-key",
        "INTENT_MODEL": "gpt-4.1-mini",
        "FOLLOWUP_MODEL": "gpt-4.1-mini",
    }):
        from config import Settings
        s = Settings()
        assert s.intent_model == "gpt-4.1-mini"
        assert s.followup_model == "gpt-4.1-mini"
