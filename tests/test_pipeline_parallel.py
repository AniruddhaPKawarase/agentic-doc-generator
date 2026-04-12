"""Tests for scope gap pipeline parallelism optimizations."""
import os
import pytest


def test_pipeline_config_defaults():
    """Pipeline config uses optimized defaults."""
    env_backup = {}
    for k in ["SCOPE_GAP_MAX_ATTEMPTS", "SCOPE_GAP_COMPLETENESS_THRESHOLD"]:
        if k in os.environ:
            env_backup[k] = os.environ.pop(k)

    try:
        from scope_pipeline.config import get_pipeline_config
        config = get_pipeline_config()
        assert config.max_attempts == 2, f"Expected 2, got {config.max_attempts}"
        assert config.completeness_threshold == 90.0, f"Expected 90.0, got {config.completeness_threshold}"
    finally:
        os.environ.update(env_backup)
