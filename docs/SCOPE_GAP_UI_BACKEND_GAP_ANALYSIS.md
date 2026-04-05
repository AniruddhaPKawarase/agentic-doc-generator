# Scope Gap Pipeline — UI vs Backend Gap Analysis

**Date:** 2026-04-05
**UI File:** `scopegap-agent-v3.html` (production UI prototype, 609 lines)
**Backend:** `scope_pipeline/` (deployed on sandbox 54.197.189.113:8003)

---

## Executive Summary

The production UI (`scopegap-agent-v3.html`) has a **3-page workflow**: Projects → Agents → Scope Workspace. The Scope Workspace has 3 views: Export (trade list), Report (per-trade scope items), and Drawing Viewer (annotated sheet with findings). Our backend satisfies **most** of the core data needs but has **9 gaps** that need attention.

| Category | Supported | Gaps | Critical Gaps |
|----------|-----------|------|--------------|
| Data/Content | 8/11 | 3 | 2 |
| UI Features | 6/10 | 4 | 1 |
| API Contract | 5/8 | 3 | 2 |
| **Total** | **19/29** | **10** | **5** |

---

## What the UI Expects vs What the Backend Provides

### Page 1: Project Selection

| UI Feature | UI Data Needed | Backend Status | Gap? |
|-----------|---------------|----------------|------|
| Project list with name, location, PM, date, status, type, progress % | Project metadata from an external source | **NOT OUR SCOPE** — UI fetches this from the main iFieldSmart app, not from the construction agent | No |
| Project search/filter | Client-side filter on project list | N/A | No |

**Verdict:** Page 1 is independent of our backend. No gap.

---

### Page 2: Agent Selection

| UI Feature | UI Data Needed | Backend Status | Gap? |
|-----------|---------------|----------------|------|
| Agent grid (RFI, Submittal, Drawings, Spec, BIM, Meeting) | Static agent list | **NOT OUR SCOPE** — UI renders static tiles. "Drawings Agent" tile triggers Page 3 | No |
| Chat input at bottom | Would call `/api/chat` (old pipeline) | Already exists | No |

**Verdict:** Page 2 is independent. No gap.

---

### Page 3: Scope Workspace — This is where gaps exist

#### 3A. Dark Sidebar (Left)

| UI Feature | UI Data Needed | Backend Status | Gap? |
|-----------|---------------|----------------|------|
| **Project name** in sidebar header | `project_name` | **GAP** — Backend returns `project_name: ""` because SQL project name lookup isn't working on sandbox (pyodbc not installed). On prod VM this works. | Minor |
| **3 tabs: Drawings / Specs / Findings** | Drawing categories, spec categories, findings list | **PARTIAL GAP** — See below | Yes |
| **Drawings tab:** Categories (GENERAL, ELECTRICAL, MECHANICAL, etc.) with expandable tree | Categorized drawing list from API | **GAP** — Backend doesn't return drawing categories. API returns flat `drawingName` list. UI needs drawings grouped by category (discipline). | **CRITICAL** |
| **Specs tab:** Same category structure for specifications | Categorized spec list | **GAP** — Same issue. Backend doesn't distinguish drawings vs specs. | **CRITICAL** |
| **Findings tab:** List of findings with count badges per drawing | `{drawing_id, label, count}` per drawing | **SUPPORTED** — Can be derived from `ScopeGapResult.items` grouped by `drawing_name` with count. Frontend computes this client-side. | No |
| **Revision dropdown** (Complete Set, 100% CD, Issued for Permit) | Revision/set metadata | **PARTIAL** — Backend supports `set_ids` filter but doesn't return a list of available revisions/sets. UI needs a `GET /api/projects/{id}/sets` endpoint. | **CRITICAL** |
| **User info** at sidebar bottom | User profile from auth | **NOT OUR SCOPE** — Phase 10 auth handles this | No |

#### 3B. Export View (Trade List)

| UI Feature | UI Data Needed | Backend Status | Gap? |
|-----------|---------------|----------------|------|
| **Trade list** with color dot and "Ready" status | List of trades + color + item count | **SUPPORTED** — `ScopeGapResult.items` grouped by trade gives count. Trade colors are client-side constants (`TC` object in UI). Status = "Ready" if count > 0. | No |
| **Trade color mapping** | `{trade: hex_color}` | **CLIENT-SIDE** — UI defines `TC` object with 23 trade colors. Backend doesn't need to provide this. | No |
| **"Export All" button** | CSV/PDF download | **SUPPORTED** — `documents.csv_path` provides CSV. | No |
| **Total scope items count** in top bar | Sum of all items | **SUPPORTED** — `pipeline_stats.items_extracted` or `len(items)` | No |
| **Project name tag** | Project name | Same minor gap as sidebar (pyodbc) | Minor |

#### 3C. Report View (Per-Trade Scope Items)

| UI Feature | UI Data Needed | Backend Status | Gap? |
|-----------|---------------|----------------|------|
| **Trade name + "Scope of Work"** header | Trade name | **SUPPORTED** — `trade` field | No |
| **"Job Specific Items"** section title | Static | N/A | No |
| **Scope items with checkboxes** | List of scope items with text | **SUPPORTED** — `items[]` with `text` field | No |
| **Source reference link (🔗) per item** | Reference to source drawing + page | **SUPPORTED** — Each item has `drawing_name`, `page`, `source_snippet` | No |
| **Click 🔗 → opens Reference Panel** with source documents | Per-item reference list with drawing IDs | **SUPPORTED** — Each item has `drawing_name`. UI can look up drawing metadata. | No |
| **Reference Panel:** Drawing cards with "Click to view highlighted drawing →" | Drawing metadata for each reference | **PARTIAL** — Backend provides `drawing_name` but NOT the full drawing metadata (sheet name, project name). UI hardcodes this in `DWG` object. | **GAP** |
| **Export button** with dropdown (per-trade) | Per-trade export files | **SUPPORTED** — `documents` has all 4 formats | No |
| **Item text formatting** — long technical descriptions with measurements | Full scope text | **SUPPORTED** — `text` field contains full extraction | No |

#### 3D. Drawing Viewer

| UI Feature | UI Data Needed | Backend Status | Gap? |
|-----------|---------------|----------------|------|
| **Drawing sheet rendering** with title block | PDF rendering or HTML mockup of drawing | **NOT BACKEND RESPONSIBILITY** — The UI renders drawings client-side (either PDF.js or HTML mockup). Backend provides data, not visuals. | No |
| **Trade-colored text annotations** on drawing | Per-finding: text, position, trade, color | **GAP** — Backend returns `source_snippet` but NOT x/y coordinates on the drawing. The UI positions annotations manually (hardcoded `style="left:30px;top:50px"`). For real drawings, this needs PDF.js text layer matching (like the JSX prototype does). | See note |
| **Findings sidebar** (left, dark) with checkboxes | Findings list per drawing | **SUPPORTED** — Items filtered by `drawing_name` | No |
| **Filter tags** (Div 07 drawing, A744) as dismissible pills | Drawing ID tags | **SUPPORTED** — `drawing_name` per item | No |
| **Toolbar:** Select, Move, Zoom, Comment, Measure, Pan, Visibility, Highlight, Capture | Client-side drawing tools | **NOT BACKEND** — All client-side functionality | No |
| **Trade/Scope dropdown** in toolbar | List of trades | **SUPPORTED** — Client-side constant | No |
| **"Draw a Highlight" button** | Saves highlight annotation | **GAP** — Backend has no endpoint to persist user-drawn highlights. Need `POST /api/scope-gap/sessions/{id}/highlights` | **GAP** |
| **Tooltip on hover** showing trade name + color | Per-annotation trade info | **SUPPORTED** — Each item has `trade` field | No |
| **Drawing title** (project name + sheet number) | Drawing metadata | **PARTIAL** — Backend returns `drawing_name` and `drawing_title` but not sheet metadata (full title, project context) | Minor |

---

## Gap Summary — 10 Items

### CRITICAL GAPS (must fix for production UI)

| # | Gap | What UI Needs | What Backend Provides | Fix Required |
|---|-----|---------------|----------------------|-------------|
| **G1** | Drawing/Spec categorization | Drawings grouped by discipline (GENERAL, ELECTRICAL, MECHANICAL, etc.) | Flat list of `drawing_name` strings | **New endpoint or field:** Either return `discipline` category per drawing from the MongoDB API, or add a classifier that maps drawing name prefixes (E=Electrical, M=Mechanical, A=Architectural, S=Structural, P=Plumbing) to categories |
| **G2** | Available revisions/sets | List of `{set_id, set_name}` for the project to populate the revision dropdown | Only accepts `set_ids` as input, doesn't list available sets | **New endpoint:** `GET /api/scope-gap/projects/{id}/sets` that calls MongoDB API to get unique set names |
| **G3** | Drawing metadata for Reference Panel | For each referenced drawing: sheet name, project name, discipline, thumbnail | Only `drawing_name` and `drawing_title` | **Enrich response:** Add drawing metadata to items or provide a drawing lookup endpoint |
| **G4** | Highlight persistence | Save user-drawn highlights (position, text, trade, critical, comments) | No highlight storage | **New endpoint:** `POST /api/scope-gap/sessions/{id}/highlights` to persist annotations |
| **G5** | Trade list endpoint | Frontend needs to know which trades have data for a project BEFORE running the pipeline | No pre-pipeline trade discovery | **New endpoint:** `GET /api/scope-gap/projects/{id}/trades` that returns trades with record counts without running the full pipeline |

### MINOR GAPS (nice to have, not blockers)

| # | Gap | Impact | Fix |
|---|-----|--------|-----|
| **G6** | Project name empty | Sidebar shows project ID instead of name | Install pyodbc on sandbox VM (already works on prod) |
| **G7** | Drawing position data | Annotations on drawing viewer need x/y coordinates | Frontend handles via PDF.js text layer matching — not a backend issue |
| **G8** | Drawings vs Specs distinction | Sidebar has separate Drawings/Specs tabs | Add `source_type` field (drawing/specification) from MongoDB `source_type` field |
| **G9** | Item re-ordering / drag-drop | UI shows items with drag handles (≡ icon) | Client-side only — persist order via session update if needed |
| **G10** | Pipeline status indicator per trade | Show which trades have been analyzed vs pending | Add `analyzed_trades` to session or a project-level status endpoint |

---

## API Contract Gaps — What's Missing

### New Endpoints Needed

```
GET /api/scope-gap/projects/{project_id}/trades
  → Returns: [{"trade": "Electrical", "record_count": 107}, {"trade": "Plumbing", "record_count": 45}, ...]
  → Purpose: Populate trade list BEFORE running pipeline

GET /api/scope-gap/projects/{project_id}/sets
  → Returns: [{"set_id": 4730, "set_name": "100% Construction Documents"}, ...]
  → Purpose: Populate revision/set dropdown in sidebar

GET /api/scope-gap/projects/{project_id}/drawings
  → Returns: [{"drawing_name": "E0.03", "drawing_title": "Schedules - Electrical", "discipline": "ELECTRICAL", "source_type": "drawing"}, ...]
  → Purpose: Populate sidebar Drawings/Specs tabs with categorized tree

POST /api/scope-gap/sessions/{session_id}/highlights
  → Body: {"drawing_name": "E0.03", "x": 30, "y": 50, "width": 200, "height": 40, "text": "captured text", "trade": "Electrical", "critical": false, "comment": ""}
  → Purpose: Persist user-drawn highlights

GET /api/scope-gap/sessions/{session_id}/highlights
  → Returns: list of saved highlights for the session
  → Purpose: Load highlights when revisiting a drawing
```

### Response Enrichment Needed

```python
# Current ScopeItem
class ScopeItem:
    drawing_name: str       # "E0.03"
    drawing_title: str      # "Schedules - Electrical"

# Needed additions
class ScopeItem:
    drawing_name: str       # "E0.03"
    drawing_title: str      # "Schedules - Electrical"
    discipline: str         # "ELECTRICAL"  ← NEW
    source_type: str        # "drawing" or "specification"  ← NEW
```

---

## Resources Needed to Fix Gaps

### For G1 (Drawing Categorization)

**Option A: Drawing name prefix mapping (simplest, no API change)**
```python
PREFIX_TO_DISCIPLINE = {
    "E": "ELECTRICAL", "M": "MECHANICAL", "P": "PLUMBING",
    "A": "ARCHITECTURAL", "S": "STRUCTURAL", "L": "LIGHTING",
    "LC": "LIGHTING", "FP": "FIRE PROTECTION", "G": "GENERAL",
}
```
Add this mapping in the DataFetcher or a utility, derive `discipline` from `drawingName` prefix.

**Option B: Use MongoDB `setTrade` field**
The API already returns `setTrade` per record. Map `setTrade` to discipline categories.

### For G2 (Available Sets)

**Source:** MongoDB API at `https://mongo.ifieldsmart.com`
**Question for user:** Is there an API endpoint that lists available sets for a project? Something like:
```
GET /api/drawingText/sets?projectId=7276
```
If not, we can derive sets from the first page of summaryByTrade results (extract unique `setId`/`setName` pairs).

### For G3 (Drawing Metadata)

**Source:** Already in the MongoDB API response — each record has `drawingName`, `drawingTitle`, `setName`, `setTrade`.
**Fix:** In DataFetcher, build a drawing metadata index from the fetched records and include it in the response.

### For G4 (Highlight Persistence)

**Storage:** Add `highlights` field to `ScopeGapSession`:
```python
class Highlight(BaseModel):
    id: str
    drawing_name: str
    x: float
    y: float
    width: float
    height: float
    text: str
    trade: str
    critical: bool = False
    comment: str = ""

class ScopeGapSession(BaseModel):
    ...
    highlights: list[Highlight] = []
```
Persisted via existing 3-layer session manager.

### For G5 (Trade Discovery)

**Source:** Query MongoDB API for a single page per known trade, check if records exist.
Or: fetch all records for the project (across all trades) and return unique trade names with counts. This could reuse the existing `summaryByTrade` call with each known trade.

---

## Clarifying Questions for User

### Q1: Drawing/Spec Source

The UI shows a categorized tree of drawings (GENERAL, ELECTRICAL, MECHANICAL, etc.) and specs. Where does this data come from in production?

- (a) The main iFieldSmart web app provides a drawing index API that we should call
- (b) We derive it from the MongoDB `summaryByTrade` API response (already available)
- (c) There's a separate API endpoint for drawing sets/sheets

### Q2: Available Sets/Revisions

The UI has a "Revision" dropdown (Complete Set, 100% Construction Documents, Issued for Permit). Where does this list come from?

- (a) MongoDB API has a sets endpoint we should call
- (b) We derive from unique `setName` values in the summaryByTrade response
- (c) It's hardcoded per project in the main app

### Q3: Drawing Viewer — Real PDFs or HTML Mockup?

The production UI renders drawings as HTML/CSS mockups (positioned `<div>` elements). Will the real production version:

- (a) Render actual PDF drawings via PDF.js (like the JSX prototype)
- (b) Keep the HTML mockup approach with annotations overlaid
- (c) Use an external drawing viewer component (like Autodesk Forge, OpenSeaDragon)

This affects whether we need to return x/y coordinates for annotations.

### Q4: Highlight Persistence — Is This MVP?

The "Draw a Highlight" feature saves user annotations on drawings. Is this needed for launch, or can it be deferred?

- (a) MVP — needed for launch
- (b) Defer to v2

### Q5: Multi-Trade in One Session

The UI shows ALL trades on the Export page (Electrical, HVAC, Plumbing, Fire Alarm, Lighting, Low Voltage, Controls, etc.). Currently our pipeline runs one trade at a time. Should we:

- (a) Run the pipeline once per trade (user clicks each trade to generate)
- (b) Auto-run all trades when the user opens the Scope Workspace
- (c) Let the user select which trades to analyze, then batch-run

---

## Priority Matrix

| Priority | Gap | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | G5: Trade discovery endpoint | 2 hours | Unlocks Export page |
| **P0** | G1: Drawing categorization | 3 hours | Unlocks Drawings/Specs sidebar tabs |
| **P1** | G2: Available sets endpoint | 2 hours | Unlocks Revision dropdown |
| **P1** | G3: Drawing metadata enrichment | 2 hours | Enables Reference Panel cards |
| **P1** | G8: source_type field | 1 hour | Separates Drawings vs Specs |
| **P2** | G4: Highlight persistence | 3 hours | Enables "Draw a Highlight" |
| **P2** | G6: Project name (pyodbc) | 30 min | Install on sandbox VM |
| **P3** | G10: Per-trade analysis status | 2 hours | Shows which trades are done |
| **N/A** | G7: Drawing position data | Frontend | PDF.js handles this |
| **N/A** | G9: Item reordering | Frontend | Client-side drag-drop |

**Total effort for P0+P1 fixes: ~10 hours**
