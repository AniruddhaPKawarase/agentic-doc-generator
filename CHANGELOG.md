# Changelog

## [2.1.0] - 2026-04-07

### Fixed
- Reference documents now display inline citations [Source: drawing, page] on each scope item
- Right panel auto-populates with source drawings after pipeline completion
- Export to Doc button works — all 4 formats (Word, PDF, CSV, JSON) download directly to browser
- Font/color visibility: neutral background (#F8FAFC), dark text (#1E293B)

### Added
- UI refactored into ~15 portable modules (scope-gap-ui/)
- Structured logging via structlog (JSON with request_id)
- Request ID middleware (X-Request-Id header)
- Rate limiting via slowapi (10/min generate, 60/min reads)
- Concurrency cap: 503 when >50 concurrent requests
- /api/scope-gap/status and /api/scope-gap/metrics endpoints
- S3 versioning enabled on production bucket
- Session backup to S3 after pipeline completion
- Input validation on document file_id
- Auth middleware for Bearer token validation
- CORS restricted to known domains
- Deploy, GitHub push, and test runner scripts
- TROUBLESHOOTING.md with error code reference

### Changed
- PARALLEL_FETCH_CONCURRENCY default: 10 -> 30
- httpx pool: max_connections=100, max_keepalive_connections=20
- Note compression: added 75-char tier for large datasets
