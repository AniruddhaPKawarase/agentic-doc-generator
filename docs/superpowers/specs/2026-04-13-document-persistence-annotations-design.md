# Design Spec: Document Persistence, Annotations, and Document Management

**Date:** 2026-04-13  
**Status:** PENDING APPROVAL  
**Agent:** Construction Intelligence Agent  
**Port:** 8003  

---

## User Story

As a user of the Construction Intelligence Agent:
1. I want generated documents to persist in S3 with a structured hierarchy (Project > Set > Trade) so they survive page refreshes
2. I want to see a list of previously generated documents for my project, filterable by set and trade, so I can re-download without regenerating
3. I want source references in the API response to include the `text` content with coordinates, so the Angular frontend can highlight relevant regions on the reference drawing PDFs
4. I want `set_ids` to be mandatory for document generation so documents are properly organized

---

## Feature 1: S3 Folder Restructuring with SetName

### Current S3 Path
```
construction-intelligence-agent/
  generated_documents/
    {ProjectName}_{ProjectID}/
      {Trade}/
        {filename}.docx
```

### New S3 Path
```
construction-intelligence-agent/
  generated_documents/
    {ProjectName}({ProjectID})/
      {SetName}({SetID})/
        {Trade}/
          {filename}.docx
```

**Example:**
```
construction-intelligence-agent/
  generated_documents/
    GranvilleHotel(7298)/
      Foundation_Plans(4730)/
        Electrical/
          scope_electrical_set4730_GranvilleHotel_7298_a1b2c3d4.docx
      Structural_Sheets(4731)/
        Electrical/
          scope_electrical_set4731_GranvilleHotel_7298_b2c3d4e5.docx
```

### Behavioral Changes

#### set_ids Mandatory for Document Generation
- `ChatRequest.set_ids` is **required** when `generate_document=True`
- If `generate_document=True` and `set_ids` is empty/None, return HTTP 422 with message: `"set_ids is required when generate_document is true"`
- If `generate_document=False` (chat-only, no doc), `set_ids` remains optional (existing behavior preserved)

#### Multiple set_ids = Separate Documents Per Set
When `set_ids=[4730, 4731]`:
1. Data fetch per set (already supported via parallel `summaryByTradeAndSet` calls)
2. Context building per set
3. LLM generation per set (one call per set for quality)
4. Document generation per set (one `.docx` per set)
5. Response includes array of `GeneratedDocument` metadata

#### Overwrite on Regeneration
When a document is regenerated for the same Project + Set + Trade:
1. Before uploading new document, list existing objects under `{Project}/{Set}/{Trade}/` prefix
2. Delete all existing `.docx` files in that prefix (via `delete_prefix` scoped to that folder)
3. Upload the new document
4. This ensures only one document exists per Project/Set/Trade combination

### SetName Resolution
- The `setName` field is available in the API response records as a human-readable string (e.g., `"Foundation Plans"`)
- Already extracted by `DataAgent` during data fetch
- Will be passed through to the document generator and S3 key builder
- Sanitized via existing `sanitize_name()` helper (spaces become underscores, special chars removed)

### Files Modified

| File | Change |
|------|--------|
| `s3_utils/helpers.py` | Update `generated_document_key()` — add `set_name: str` and `set_id: int` params, insert set folder |
| `services/document_generator.py` | Pass `set_name`/`set_id` to S3 key builder. Add overwrite logic (delete existing before upload) |
| `services/exhibit_document_generator.py` | Same changes as `document_generator.py` |
| `agents/generation_agent.py` | When multiple `set_ids`: loop per set, generate separate document per set. Validate `set_ids` required when `generate_document=True` |
| `models/schemas.py` | Add validation: `set_ids` required when `generate_document=True`. `ChatResponse.document` remains singular (one response per set when split), or add `documents: list[GeneratedDocument]` field |

### `generated_document_key()` New Signature
```python
def generated_document_key(
    agent_prefix: str,
    project_name: str | None,
    project_id: int,
    set_name: str,        # NEW — human-readable set name
    set_id: int,          # NEW — set ID for uniqueness
    trade: str,
    filename: str,
) -> str:
    """
    Build S3 key:
    {agent}/generated_documents/{ProjectName}({ProjectID})/{SetName}({SetID})/{Trade}/{filename}
    """
    project_folder = f"{sanitize_name(project_name)}({project_id})" if project_name else f"Project({project_id})"
    set_folder = f"{sanitize_name(set_name)}({set_id})"
    trade_folder = sanitize_name(trade) if trade else "General"
    return f"{agent_prefix}/generated_documents/{project_folder}/{set_folder}/{trade_folder}/{filename}"
```

---

## Feature 2: Source References `annotations` Array with `text`

### Current Schema (source_references in ChatResponse)
```json
{
  "A-12": {
    "drawing_id": 12345,
    "drawing_name": "A-12",
    "drawing_title": "ELECTRICAL FLOOR PLAN",
    "s3_url": "https://agentic-ai-production.s3.amazonaws.com/ifieldsmart/proj/Drawings/pdf/pdfA12.pdf",
    "pdf_name": "pdfA12",
    "x": 100,
    "y": 200,
    "width": 50,
    "height": 30
  }
}
```

### New Schema (backward-compatible addition)
```json
{
  "A-12": {
    "drawing_id": 12345,
    "drawing_name": "A-12",
    "drawing_title": "ELECTRICAL FLOOR PLAN",
    "s3_url": "https://agentic-ai-production.s3.amazonaws.com/ifieldsmart/proj/Drawings/pdf/pdfA12.pdf",
    "pdf_name": "pdfA12",
    "x": 100,
    "y": 200,
    "width": 50,
    "height": 30,
    "text": "Panel EP-1, 200A, 3-phase",
    "annotations": [
      {
        "text": "Panel EP-1, 200A, 3-phase",
        "x": 100,
        "y": 200,
        "width": 50,
        "height": 30
      },
      {
        "text": "Conduit run from Panel EP-1 to MDP",
        "x": 300,
        "y": 150,
        "width": 40,
        "height": 20
      }
    ]
  }
}
```

### Backward Compatibility Strategy
- **Root-level `x`, `y`, `width`, `height`** — preserved from the FIRST annotation (or first record). Existing consumers that read these fields see no change
- **Root-level `text`** — NEW additive field, value from first annotation. Consumers that don't use it simply ignore it
- **`annotations` array** — NEW additive field containing ALL text+coordinate pairs for this drawing. Angular frontend uses this for multi-region highlighting

### Data Source
- `text` comes from `DrawingRecord.text` — the raw note/annotation content from the MongoDB API
- Each API record has its own `text`, `x`, `y`, `width`, `height` for a specific annotation on a drawing
- Multiple records can reference the same `drawingName` with different text/coordinates

### Implementation

#### New `Annotation` Dataclass
```python
@dataclass(frozen=True, slots=True)
class Annotation:
    """Single text annotation with coordinates on a drawing."""
    text: str
    x: int | None
    y: int | None
    width: int | None
    height: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

#### Updated `SourceReference` Dataclass
```python
@dataclass(frozen=True, slots=True)
class SourceReference:
    drawing_id: int
    drawing_name: str
    drawing_title: str
    s3_url: str
    pdf_name: str
    x: int | None              # First annotation's x (backward compat)
    y: int | None              # First annotation's y (backward compat)
    width: int | None          # First annotation's width (backward compat)
    height: int | None         # First annotation's height (backward compat)
    text: str                  # NEW: First annotation's text (backward compat)
    annotations: tuple[Annotation, ...]  # NEW: All annotations

    def to_dict(self) -> dict[str, Any]:
        d = {
            "drawing_id": self.drawing_id,
            "drawing_name": self.drawing_name,
            "drawing_title": self.drawing_title,
            "s3_url": self.s3_url,
            "pdf_name": self.pdf_name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            "annotations": [a.to_dict() for a in self.annotations],
        }
        return d
```

#### Updated `SourceIndexBuilder.build()`
Current behavior: one record per drawing (first seen wins, dedup by `drawingName`).

New behavior:
1. **Group all records by `drawingName`** (not dedup — collect all)
2. For each drawing group:
   - Extract S3 URL from first record with valid `s3BucketPath`/`pdfName`
   - Collect ALL text+coordinate pairs as `Annotation` objects
   - Set root-level `x`, `y`, `width`, `height`, `text` from first annotation
3. Return `SourceReference` with `annotations` tuple

```python
def build(self, records: list[dict]) -> tuple[dict[str, SourceReference], dict[str, Any]]:
    # Group records by drawingName
    by_drawing: dict[str, list[dict]] = {}
    for rec in records:
        dn = (rec.get("drawingName") or "").strip()
        if dn:
            by_drawing.setdefault(dn, []).append(rec)

    index: dict[str, SourceReference] = {}
    for dn, group in by_drawing.items():
        # Find first record with valid S3 info
        s3_url, pdf_name, drawing_id, drawing_title = "", "", 0, ""
        for rec in group:
            s3_path_raw = rec.get("s3BucketPath", "")
            pn = rec.get("pdfName", "")
            if s3_path_raw and pn:
                s3_path = self._sanitize_s3_path(s3_path_raw)
                safe_pdf = self._sanitize_pdf_name(pn)
                if s3_path and safe_pdf:
                    s3_url = self._build_s3_url(s3_path, safe_pdf)
                    pdf_name = pn
                    drawing_id = self._safe_drawing_id(rec.get("drawingId"))
                    drawing_title = rec.get("drawingTitle", "")
                    break

        if not s3_url:
            continue  # Skip drawings without valid S3 source

        # Build annotations from ALL records in this drawing group
        annotations = []
        for rec in group:
            text = (rec.get("text") or "").strip()
            x, y, w, h = self._validate_coordinates(rec)
            if text:  # Only include annotations that have text
                annotations.append(Annotation(text=text, x=x, y=y, width=w, height=h))

        # Root-level values from first annotation (backward compat)
        first = annotations[0] if annotations else Annotation(text="", x=None, y=None, width=None, height=None)

        index[dn] = SourceReference(
            drawing_id=drawing_id,
            drawing_name=dn,
            drawing_title=drawing_title,
            s3_url=s3_url,
            pdf_name=pdf_name,
            x=first.x, y=first.y, width=first.width, height=first.height,
            text=first.text,
            annotations=tuple(annotations),
        )

    return index, metadata
```

### Files Modified

| File | Change |
|------|--------|
| `services/source_index.py` | Add `Annotation` dataclass. Update `SourceReference` with `text` and `annotations`. Rewrite `build()` to group all records per drawing |
| `services/document_generator.py` | Update `_add_traceability_table()` to show text column |
| `models/schemas.py` | Update `ChatResponse.source_references` description to reflect new fields |

---

## Feature 3: Document Listing API Enhancement

### Current Endpoint
```
GET /api/documents/list?project_id=7298&trade=Electrical
```

### Enhanced Endpoint
```
GET /api/documents/list?project_id=7298&set_name=Foundation_Plans&trade=Electrical
```

### Parameter Changes
| Parameter | Required? | Type | Description |
|-----------|-----------|------|-------------|
| `project_id` | **YES** (was optional) | int | Filter documents for this project |
| `set_name` | No | str | Filter by set name (partial match, case-insensitive) |
| `trade` | No | str | Filter by trade name |

### Response Schema Update
Each document object gains `set_name` and `set_id` fields:
```json
{
  "success": true,
  "data": {
    "documents": [
      {
        "file_id": "a1b2c3d4",
        "filename": "scope_electrical_set4730_GranvilleHotel_7298_a1b2c3d4.docx",
        "s3_key": "construction-intelligence-agent/generated_documents/GranvilleHotel(7298)/Foundation_Plans(4730)/Electrical/...",
        "project_folder": "GranvilleHotel(7298)",
        "project_id": 7298,
        "set_name": "Foundation Plans",
        "set_id": 4730,
        "trade": "Electrical",
        "size_bytes": 42872,
        "size_kb": 41.9,
        "download_url": "https://ai5.ifieldsmart.com/construction/api/documents/a1b2c3d4/download",
        "created_at": "2026-04-13T09:00:00Z",
        "storage": "s3"
      }
    ],
    "total": 1
  }
}
```

### S3 Key Parsing Update
Current parsing expects 3 parts: `{ProjectFolder}/{Trade}/{filename}`
New parsing expects 4 parts: `{ProjectFolder}/{SetFolder}/{Trade}/{filename}`

```python
# Parse: {ProjectName}({ProjectID})/{SetName}({SetID})/{Trade}/{filename}
parts = key.replace(prefix, "").split("/")
if len(parts) < 4:
    continue  # Skip legacy 3-level structure or invalid keys

project_folder = parts[0]   # "GranvilleHotel(7298)"
set_folder = parts[1]       # "Foundation_Plans(4730)"
trade_folder = parts[2]     # "Electrical"
filename = parts[3]

# Extract project_id from "GranvilleHotel(7298)"
project_id_match = re.search(r'\((\d+)\)$', project_folder)
doc_project_id = int(project_id_match.group(1)) if project_id_match else 0

# Extract set_id and set_name from "Foundation_Plans(4730)"
set_id_match = re.search(r'\((\d+)\)$', set_folder)
doc_set_id = int(set_id_match.group(1)) if set_id_match else 0
doc_set_name = re.sub(r'\(\d+\)$', '', set_folder).replace('_', ' ').strip()
```

### Backward Compatibility with Old Documents
Documents uploaded before this change have the old 3-level structure. The parser checks `len(parts)`:
- `>= 4` parts: new structure, extract set info
- `3` parts: legacy structure, set `set_name="Unknown"`, `set_id=0`
- `< 3` parts: skip (invalid)

### Files Modified

| File | Change |
|------|--------|
| `routers/documents.py` | Make `project_id` required. Add `set_name` filter. Update S3 key parsing for 4-level structure. Include `set_name`/`set_id` in response |

---

## Feature 4: Angular Frontend Guidance (Document Persistence)

### Root Cause
The backend persists documents to S3 correctly. The Angular frontend stores the document reference in component state, which is lost on page refresh.

### Recommended Frontend Solution

#### Option A: Call Document List API on Component Init (Recommended)
```typescript
// In Angular component that displays the document
ngOnInit() {
  this.loadExistingDocuments();
}

async loadExistingDocuments() {
  const docs = await this.http.get(
    `/construction/api/documents/list?project_id=${this.projectId}`
  ).toPromise();
  
  if (docs.data.documents.length > 0) {
    this.documents = docs.data.documents;
    // User can see and download any previously generated document
  }
}
```

#### Option B: Store in localStorage as Backup
```typescript
// After successful document generation
onDocumentGenerated(response: ChatResponse) {
  if (response.document) {
    const key = `doc_${response.document.project_id}_${response.document.trade}`;
    localStorage.setItem(key, JSON.stringify(response.document));
  }
}

// On component init, check localStorage first, then API
ngOnInit() {
  const cached = localStorage.getItem(`doc_${this.projectId}_${this.trade}`);
  if (cached) {
    this.document = JSON.parse(cached);
  }
  // Always refresh from API to get latest
  this.loadExistingDocuments();
}
```

**Recommendation:** Option A is cleaner — always call the list API. The backend is the source of truth.

---

## Non-Goals (Explicitly Excluded)

1. **No frontend code changes** — Angular is external, we provide API + guidance only
2. **No new API versioning** — all changes are additive/backward-compatible
3. **No database** — document metadata is derived from S3 folder structure (existing pattern)
4. **No changes to LLM pipeline** — intent detection, context building, generation unchanged
5. **No changes to scope-gap pipeline** — only affects chat pipeline document generation
6. **No changes to session/caching/Redis** — these layers are untouched

---

## Testing Strategy

### Unit Tests (new test file: `tests/test_document_persistence.py`)
1. `test_generated_document_key_with_set` — verify new S3 key format
2. `test_generated_document_key_set_name_sanitization` — special chars in set names
3. `test_source_reference_annotations` — verify annotations array built correctly
4. `test_source_reference_backward_compat` — root-level x/y/width/height still present
5. `test_source_reference_text_field` — text extracted from DrawingRecord.text
6. `test_multiple_annotations_per_drawing` — multiple records for same drawing
7. `test_set_ids_required_for_doc_generation` — 422 when missing
8. `test_document_overwrite` — old doc deleted before new upload
9. `test_document_list_with_set_filter` — set_name filter works
10. `test_document_list_legacy_compatibility` — old 3-level docs still listed

### Integration Tests
1. Generate document with set_id, verify S3 key structure
2. List documents with project_id + set_name filter
3. Regenerate same Project/Set/Trade, verify only one document exists
4. Generate with multiple set_ids, verify separate documents per set

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Old documents with 3-level structure break listing | Parser handles both 3-level (legacy) and 4-level (new) |
| Source reference schema change breaks Angular | Additive only — new fields added, old fields preserved |
| Multiple set_ids makes response time 2x-3x slower | Each set generates in parallel (asyncio.gather) |
| Set name not available in API response | Fallback: use `Set_{set_id}` if `setName` field is empty |
| Overwrite deletes wrong files | Scoped to exact `{Project}/{Set}/{Trade}/` prefix, only `.docx` |

---

## Deployment Plan

### Phase 1: Backend Changes (Local Development)
1. Update `s3_utils/helpers.py` — new key builder
2. Update `services/source_index.py` — annotations + text
3. Update `services/document_generator.py` — set folder + overwrite
4. Update `services/exhibit_document_generator.py` — same
5. Update `agents/generation_agent.py` — per-set generation loop, set_ids validation
6. Update `routers/documents.py` — set_name filter, 4-level parsing, project_id required
7. Update `models/schemas.py` — validation, field descriptions
8. Write tests, run full test suite

### Phase 2: Sandbox Deployment (54.197.189.113)
1. SSH to sandbox, sync code to `/home/ubuntu/chatbot/aniruddha/vcsai/`
2. Same S3 bucket, same MongoDB API
3. Run integration tests against sandbox
4. Verify document generation, listing, download

### Phase 3: Production Deployment (13.217.22.125)
1. SSH to prod, sync code to `/home/ubuntu/vcsai/`
2. Restart construction-agent service
3. Verify via health check + test document generation

### Phase 4: Post-Deployment
1. Update `docs/PRODUCTION_API_REFERENCE.md`
2. Create sandbox API reference file
3. Save test results (docx + JSON with response times/tokens)
4. Update Excel attendance sheet
5. Push to GitHub
