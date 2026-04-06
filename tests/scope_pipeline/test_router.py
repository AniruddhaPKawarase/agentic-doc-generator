"""tests/scope_pipeline/test_router.py — Route registration and endpoint verification."""

from scope_pipeline.routers.scope_gap import router

_PREFIX = "/api/scope-gap"


def _paths() -> list[str]:
    return [r.path for r in router.routes]


def _methods_by_path() -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for route in router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", set())
        if path:
            result.setdefault(path, set()).update(methods)
    return result


def test_router_has_all_pipeline_endpoints():
    """All pipeline execution endpoints are registered."""
    paths = _paths()
    assert f"{_PREFIX}/generate" in paths
    assert f"{_PREFIX}/stream" in paths
    assert f"{_PREFIX}/submit" in paths


def test_router_has_all_job_endpoints():
    """All job management endpoints are registered."""
    paths = _paths()
    assert f"{_PREFIX}/jobs" in paths
    assert f"{_PREFIX}/jobs/{{job_id}}/status" in paths
    assert f"{_PREFIX}/jobs/{{job_id}}/result" in paths
    assert f"{_PREFIX}/jobs/{{job_id}}/continue" in paths
    mbp = _methods_by_path()
    assert "DELETE" in mbp.get(f"{_PREFIX}/jobs/{{job_id}}", set())


def test_router_has_all_session_endpoints():
    """All session management endpoints are registered."""
    paths = _paths()
    assert f"{_PREFIX}/sessions" in paths
    assert f"{_PREFIX}/sessions/{{session_id}}" in paths
    mbp = _methods_by_path()
    assert "DELETE" in mbp.get(f"{_PREFIX}/sessions/{{session_id}}", set())


def test_router_has_user_decision_endpoints():
    """All user-decision endpoints are registered."""
    paths = _paths()
    assert f"{_PREFIX}/sessions/{{session_id}}/resolve-ambiguity" in paths
    assert f"{_PREFIX}/sessions/{{session_id}}/acknowledge-gotcha" in paths
    assert f"{_PREFIX}/sessions/{{session_id}}/ignore-item" in paths
    assert f"{_PREFIX}/sessions/{{session_id}}/restore-item" in paths


def test_router_has_chat_endpoint():
    """Chat follow-up endpoint is registered."""
    paths = _paths()
    assert f"{_PREFIX}/sessions/{{session_id}}/chat" in paths


def test_router_prefix():
    """Router uses the correct API prefix."""
    assert router.prefix == _PREFIX


def test_router_tags():
    """Router is tagged correctly for OpenAPI docs."""
    assert "scope-gap" in router.tags


def test_total_endpoint_count():
    """Verify the expected number of route handlers: 3 + 5 + 3 + 4 + 1 = 16."""
    paths = _paths()
    assert len(paths) == 16
