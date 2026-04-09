"""
services/sql_service.py  —  SQL Server project name lookup.

Uses pyodbc (sync) wrapped in asyncio.to_thread() — same pattern as document_generator.py.
Results cached for cache_ttl_project_name seconds (default 3600 = 1 hour) via CacheService.

On any failure, returns a usable fallback display string with the reason:
  Success : "Granville Hotel (ID: 7298)"
  Failure : "Project ID: 7298 (name lookup failed: connection timeout)"

Query: SELECT ProjectName FROM Projects WHERE projectid = ?
Database: SQL-Intelligence-Agent .env credentials (iFMasterDatabase_1)
"""

import asyncio
import logging
from typing import Optional, Tuple

from config import get_settings
from services.cache_service import CacheService

logger = logging.getLogger(__name__)
settings = get_settings()


def _format_display_name(
    project_name: Optional[str],
    project_id: int,
    error_reason: Optional[str],
) -> str:
    """Build the canonical display string used everywhere in the app."""
    if project_name:
        return f"{project_name} (ID: {project_id})"
    if error_reason:
        return f"Project ID: {project_id} (name lookup failed: {error_reason})"
    return f"Project ID: {project_id}"


class SQLService:
    """
    Lightweight SQL Server client — project name lookups only.

    Architecture:
      - Single persistent pyodbc connection, lazy-initialized on first query
      - Liveness check before each query; reconnects automatically on dead connection
      - All sync pyodbc work runs in asyncio.to_thread() — event loop never blocked
      - Results cached 1 hour via CacheService (project names are stable)
      - Graceful degradation if pyodbc or ODBC Driver 17 is missing
    """

    def __init__(self, cache: CacheService) -> None:
        self._cache = cache
        self._conn = None           # pyodbc.Connection — None until first query
        self._available: bool = True

        # Detect missing pyodbc at startup so the warning appears once, early.
        try:
            import pyodbc  # noqa: F401
        except ImportError:
            self._available = False
            logger.warning(
                "pyodbc not installed — SQL project name lookup disabled. "
                "Install with: pip install pyodbc  "
                "(ODBC Driver 17 for SQL Server must also be present on the host)"
            )

    # ── Public async API ──────────────────────────────────────────────────

    async def get_project_name(
        self, project_id: int
    ) -> Tuple[str, Optional[str]]:
        """
        Return (display_name, error_reason) for project_id.

        display_name is ALWAYS a non-empty string suitable for use in documents,
        filenames, and API responses:
          "Granville Hotel (ID: 7298)"                               — success
          "Project ID: 7298 (name lookup failed: connection timeout)" — failure

        error_reason is None on success, a human-readable string on failure.
        """
        if not self._available or not settings.sql_server_host:
            reason = "SQL not configured"
            return _format_display_name(None, project_id, reason), reason

        # Check cache first — avoids a SQL round-trip on repeated requests
        cache_key = f"project_name:{project_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit project_name project_id=%s", project_id)
            return cached, None

        # Run sync SQL query in a thread so the event loop stays unblocked
        project_name, error_reason = await asyncio.to_thread(
            self._query_sync, project_id
        )

        display_name = _format_display_name(project_name, project_id, error_reason)

        # Only cache successful lookups — transient errors should retry on next request
        if project_name:
            await self._cache.set(
                cache_key,
                display_name,
                ttl=settings.cache_ttl_project_name,
            )

        return display_name, error_reason

    async def get_project_display_info(
        self, project_id: int
    ) -> dict[str, str]:
        """Return project name and city for document headers.

        Returns:
            {"name": "SINGH RESIDENCE", "city": "Nashville"}
            Falls back to {"name": "Project {id}", "city": ""} on failure.
        """
        if not self._available or not settings.sql_server_host:
            return {"name": f"Project {project_id}", "city": ""}

        cache_key = f"project_info:{project_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached

        info = await asyncio.to_thread(self._query_project_info_sync, project_id)
        if info["name"] != f"Project {project_id}":
            await self._cache.set(cache_key, info, ttl=settings.cache_ttl_project_name)
        return info

    def _query_project_info_sync(self, project_id: int) -> dict[str, str]:
        """Sync query for project name + city. Called via to_thread."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ProjectName, City FROM Projects WHERE ProjectID = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                name = str(row[0]).strip()
                city = str(row[1]).strip() if row[1] else ""
                return {"name": name, "city": city}
            return {"name": f"Project {project_id}", "city": ""}
        except Exception as exc:
            logger.warning("get_project_display_info failed for %s: %s", project_id, exc)
            self._conn = None
            return {"name": f"Project {project_id}", "city": ""}

    async def close(self) -> None:
        """Close SQL connection on application shutdown."""
        if self._conn is not None:
            try:
                await asyncio.to_thread(self._conn.close)
            except Exception:
                pass
            self._conn = None

    # ── Internal sync helpers (run in thread pool) ────────────────────────

    @staticmethod
    def _resolve_driver() -> str:
        """
        Return the best available SQL Server ODBC driver name.

        Preference order: configured driver → ODBC Driver 18 → ODBC Driver 17 → SQL Server.
        Logs the selected driver so mismatches are immediately visible in startup logs.
        """
        try:
            import pyodbc
            available = pyodbc.drivers()
        except Exception:
            return settings.sql_driver  # fallback — pyodbc will report the real error later

        # 1. Use configured driver if it's actually installed
        if settings.sql_driver in available:
            return settings.sql_driver

        logger.warning(
            "Configured SQL_DRIVER %r not found in installed drivers: %s",
            settings.sql_driver, available,
        )

        # 2. Auto-select best available SQL Server driver (newest first)
        for preferred in (
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 13 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server",
        ):
            if preferred in available:
                logger.info("Auto-selected SQL driver: %r", preferred)
                return preferred

        logger.error(
            "No SQL Server ODBC driver found. Installed drivers: %s. "
            "Install from: https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server",
            available,
        )
        return settings.sql_driver  # return configured value; connection will fail with clear error

    def _build_conn_str(self) -> str:
        driver = self._resolve_driver()
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={settings.sql_server_host},{settings.sql_server_port};"
            f"DATABASE={settings.sql_database};"
            f"UID={settings.sql_username};"
            f"PWD={settings.sql_password};"
            f"Connection Timeout={settings.sql_connection_timeout};"
            # ODBC Driver 18 changed default to strict SSL validation.
            # TrustServerCertificate=yes is required for RDS/self-signed certs.
            # Encrypt=yes keeps the connection encrypted (data-in-transit security).
            "Encrypt=yes;TrustServerCertificate=yes;"
        )

    def _get_connection(self):
        """
        Return a live pyodbc connection, reconnecting if the existing one is dead.
        Always called from within a thread (via asyncio.to_thread).
        """
        import pyodbc

        if self._conn is None:
            logger.debug("SQL: opening new connection to %s", settings.sql_server_host)
            self._conn = pyodbc.connect(self._build_conn_str(), autocommit=True)
            return self._conn

        # Liveness check — a dead connection raises immediately here
        try:
            self._conn.cursor().execute("SELECT 1")
            return self._conn
        except Exception:
            logger.debug("SQL: connection dead — reconnecting")
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            self._conn = pyodbc.connect(self._build_conn_str(), autocommit=True)
            return self._conn

    def _query_sync(self, project_id: int) -> Tuple[Optional[str], Optional[str]]:
        """
        Run the project name query synchronously.
        Returns (project_name, error_reason).
        Called exclusively via asyncio.to_thread().
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ProjectName FROM Projects WHERE projectid = ?",
                (project_id,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                name = str(row[0]).strip()
                logger.info(
                    "SQL project name lookup: project_id=%s → %r", project_id, name
                )
                return name, None
            logger.info(
                "SQL project name lookup: no row for project_id=%s", project_id
            )
            return None, f"no record found for projectid={project_id}"

        except Exception as exc:
            raw = str(exc)
            # Redact credentials from log output
            redacted = raw.replace(settings.sql_password, "***")
            logger.warning(
                "SQL project name lookup failed project_id=%s: %s",
                project_id, redacted,
            )
            # Reset so next call gets a fresh connection attempt
            self._conn = None
            return None, self._classify_error(raw)

    @staticmethod
    def _classify_error(raw: str) -> str:
        """Convert a raw exception string into a short human-readable reason."""
        lower = raw.lower()
        if "timeout" in lower or "timed out" in lower:
            return "connection timeout"
        if "login failed" in lower or "password" in lower or "authentication" in lower:
            return "authentication error"
        if "im002" in lower or "data source name not found" in lower:
            return "ODBC driver name mismatch (check SQL_DRIVER in .env)"
        if "network" in lower or "server" in lower or "tcp" in lower:
            return "network unreachable"
        if "driver" in lower or "odbc" in lower:
            return "ODBC driver not installed"
        return "SQL error"
