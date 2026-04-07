# Agent Folder Restructure Design

**Date:** 2026-04-07
**Status:** Approved
**Scope:** `PROD_SETUP/construction-intelligence-agent/`

## Goal

Clean up the construction-intelligence-agent folder by separating core agent infrastructure from ancillary files (prototypes, generated outputs, media, one-time scripts). Archive non-infrastructure files locally via an `_archive/` subfolder. Delete auto-regenerated cache files.

## Keep (Agent Infrastructure + Documentation)

### Core Application
- `main.py` — FastAPI entry point
- `config.py` — Pydantic settings
- `requirements.txt` — Dependencies
- `.env`, `.env.example`, `.gitignore`, `LICENSE`

### Agent Infrastructure Directories
- `agents/` — Intent, data, generation agents (3 files)
- `services/` — API client, cache, context builder, session, token tracker, document generators, SQL service, hallucination guard (9 files)
- `models/` — Pydantic schemas (1 file)
- `routers/` — Chat, documents, projects endpoints (3 files)
- `utils/` — Text processor, token counter (2 files)
- `scope_pipeline/` — Phase 11 seven-agent system (entire tree, ~30 files)
- `s3_utils/` — AWS S3 integration (4 files)
- `tests/` — Full test suite, 56 tests, 77% coverage (~29 files)

### Documentation
- `README.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `SETUP.md`
- `OPTIMIZATION_DESIGN_v2.md`, `DEVELOPMENT_PLAN_v3.md`
- `DEVELOPMENT_PLAN_SETID_FEATURE.md`, `claude_chat_requirements.md`
- `docs/` — Existing docs folder (includes specs)

## Archive to `_archive/`

| File/Folder | Size | Reason |
|---|---|---|
| `ifieldsmart-scope-ai.jsx` | 64 KB | React UI prototype, not integrated |
| `scopegap-agent-v3.html` | 67 KB | HTML demo prototype |
| `scope-gap-ui/` | ~2.1K LOC | Standalone Streamlit demo app |
| `scripts/migrate_docs_to_s3.py` | ~100 LOC | One-time migration, already executed |
| `generated_docs/` | ~300 MB | Generated .docx outputs, now stored in S3 |
| `scope_Electrical_SINGHRESIDENCE_7276_6ffd56e9.docx` | 39 KB | Sample output file |
| `WhatsApp Video 2026-04-05 at 10.40.02.mp4` | ~1.8 GB | Meeting recording |
| `WhatsApp Video 2026-04-05 at 10.40.03.mp4` | ~1.7 GB | Meeting recording |
| `WhatsApp Video 2026-04-05 at 10.40.03 (1).mp4` | ~1.8 GB | Meeting recording |

Archive preserves original file paths:
```
_archive/
├── ifieldsmart-scope-ai.jsx
├── scopegap-agent-v3.html
├── scope-gap-ui/
├── scripts/
│   └── migrate_docs_to_s3.py
├── generated_docs/
├── scope_Electrical_SINGHRESIDENCE_7276_6ffd56e9.docx
└── WhatsApp Video 2026-04-05 at 10.40.02.mp4
    (+ 2 more videos)
```

## Delete (Auto-Regenerated)

| File/Folder | Reason |
|---|---|
| `.coverage` | Regenerates with `pytest --cov` |
| `.pytest_cache/` | Regenerates on test run |
| `__pycache__/` (all locations) | Python bytecode cache |

## Additional Changes

- Add `_archive/` to `.gitignore` to prevent it from bloating the repository

## Implementation Steps

1. Create `_archive/` directory
2. Move archived files/folders into `_archive/`
3. Delete `.coverage`, `.pytest_cache/`, all `__pycache__/` directories
4. Add `_archive/` to `.gitignore`
5. Verify the application still runs (imports, config intact)

## Result

After restructuring, the project root contains only:
- Application code (agents, services, models, routers, utils, scope_pipeline, s3_utils)
- Configuration (main.py, config.py, .env, requirements.txt)
- Tests
- Documentation
- Archive subfolder (gitignored)
