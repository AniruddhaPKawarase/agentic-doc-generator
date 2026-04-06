# Scope Gap Pipeline — Clarifying Questions for Production UI Alignment

**Date:** 2026-04-05
**Context:** Gap analysis between production UI (`scopegap-agent-v3.html`) and backend (`scope_pipeline/`)
**Related:** `docs/SCOPE_GAP_UI_BACKEND_GAP_ANALYSIS.md`
**Status:** AWAITING ANSWERS — Answer inline after each question, then share back

---

## Priority: CRITICAL (Q1–Q5)

These directly determine which backend gaps can be closed and how.

---

### Q1: Drawing/Spec Source

The UI shows a categorized tree of drawings (GENERAL, ELECTRICAL, MECHANICAL, etc.) and specs in the sidebar. Where does this data come from in production?

- (a) The main iFieldSmart web app provides a drawing index API that we should call
- (b) We derive it from the MongoDB `summaryByTrade` API response (each record has `drawingName`, `setTrade`)
- (c) There's a separate API endpoint for drawing sets/sheets

**Answer:** ption c
---

### Q2: Available Sets/Revisions

The UI has a "Revision" dropdown (Complete Set, 100% Construction Documents, Issued for Permit). Where does this list come from?

- (a) MongoDB API has a sets endpoint we should call
- (b) We derive from unique `setName` values in the summaryByTrade response
- (c) It's hardcoded per project in the main app
  (d) There's a separate API endpoint for drawing sets/sheets

**Answer:** option C
---

### Q3: Drawing Viewer — Real PDFs or HTML Mockup?

The production UI renders drawings as HTML/CSS mockups (positioned `<div>` elements). Will the real production version:

- (a) Render actual PDF drawings via PDF.js (like the JSX prototype)
- (b) Keep the HTML mockup approach with annotations overlaid
- (c) Use an external drawing viewer component (like Autodesk Forge, OpenSeaDragon)

This affects whether the backend needs to return x/y coordinates for annotations.

**Answer:**
option C
---

### Q4: Highlight Persistence — Is This MVP?

The "Draw a Highlight" feature saves user annotations on drawings. Is this needed for launch, or can it be deferred?

- (a) MVP — needed for launch
- (b) Defer to v2

**Answer:**
OPTION a
---

### Q5: Multi-Trade in One Session

The UI shows ALL trades on the Export page (Electrical, HVAC, Plumbing, Fire Alarm, Lighting, Low Voltage, etc.). Currently our pipeline runs one trade at a time. Should we:

- (a) Run the pipeline once per trade (user clicks each trade individually to generate)
- (b) Auto-run all trades when the user opens the Scope Workspace
- (c) Let the user select which trades to analyze, then batch-run them in parallel

**Answer:**
opton b
---

## Priority: IMPORTANT (Q6–Q10)

These affect the API contract and data shape the frontend consumes.

---

### Q6: Trade Color Mapping — Backend or Frontend?

The UI defines 23 trade colors in a `TC` object (Electrical=#F48FB1, HVAC=#90A4AE, etc.). Should the backend:

- (a) Return trade colors in the API response (backend owns the palette)
- (b) Keep colors client-side only (frontend owns the palette, as in the current UI)

**Answer:**
option a
---

### Q7: Scope Items — Checkbox State Persistence

The Report view has checkboxes next to each scope item (checked = included in export, unchecked = excluded). Should unchecking an item:

- (a) Use the existing `/ignore-item` endpoint (persisted in session)
- (b) Be client-side only (not persisted, resets on reload)

**Answer:**
option b
---

### Q8: Reference Panel Sources

When the user clicks the 🔗 link on a scope item, the Reference Panel opens showing "Source Documents" — cards for each referenced drawing. The current UI hardcodes a `refs` array per item (e.g., `["E0.03", "E0.03-AP4", "E0.03-AP7"]`). Our backend returns one `drawing_name` per item. Should we:

- (a) Return multiple `drawing_refs: list[str]` per item (one item can reference multiple drawings)
- (b) Keep single `drawing_name` per item (current behavior — one source per item)
- (c) Add a separate "related drawings" field derived from the same CSI code or trade

**Answer:**
option a
---

### Q9: Export Format in Production

The UI has an "Export" button with a dropdown arrow (▾). What export formats does the production UI need?

- (a) Word only (current old pipeline behavior)
- (b) Word + PDF (for email distribution to subs)
- (c) Word + PDF + CSV + JSON (all 4, as currently built)
- (d) Word + PDF + Excel (.xlsx with trade-by-trade sheets) instead of CSV

**Answer:**
option b
---

### Q10: Findings Count per Drawing

The Findings sidebar tab shows badge counts per drawing (e.g., "E0.03 SCHEDULES - ELECTRICAL **14**"). Should this count:

- (a) Come from the pipeline result (count items grouped by `drawing_name`)
- (b) Be a pre-computed field in the API response
- (c) Include items from ALL trades (not just the currently selected trade)

**Answer:**
option a
---

## Priority: NICE TO HAVE (Q11–Q15)

These affect UX behavior and can be decided later if needed.

---

### Q11: Pipeline Trigger UX

In the production UI, how does the user trigger scope extraction?

- (a) User selects project → agent → trade → clicks "Generate" (explicit, like our current API)
- (b) Pipeline auto-runs when user opens the Scope Workspace (automatic)
- (c) User clicks "Refresh All" button on the Export page (batch all trades)
- (d) Pipeline runs in background on project creation (pre-computed, always ready)

**Answer:**
option b and d
---

### Q12: Drawing Viewer — Findings Sidebar Behavior

The Drawing Viewer has a dark sidebar with findings checkboxes. When a finding is checked/unchecked:

- (a) It shows/hides the annotation on the drawing (visual toggle only, not persisted)
- (b) It includes/excludes the finding from the scope report (persisted)
- (c) Both — visual toggle AND persistence

**Answer:**
opton a
---

### Q13: Who Are the 23 Trades?

The UI defines 23 trades (Electrical, HVAC, Plumbing, Fire Alarm, Fire Sprinkler, Lighting, Low Voltage, Controls, Concrete, Structural Steel, Framing & Drywall, Doors & Hardware, Glass & Glazing, Roofing, Elevators, Painting, Flooring, Casework, Earthwork, Abatement, Acoustical Ceilings, Data & Telecom, General Conditions). Our pipeline currently accepts any trade string. Should we:

- (a) Hardcode the 23-trade list in the backend and validate against it
- (b) Keep accepting any string (flexible, frontend defines the list)
- (c) Fetch available trades dynamically from the MongoDB data per project

**Answer:**
option c
---

### Q14: Scope Item Text Length

The UI shows long technical descriptions (50-100 words per item). The current extraction agent returns variable-length text. Is there a preferred:

- (a) No limit — return full extraction as-is
- (b) Target 50-100 words per item (matching the UI prototype data)
- (c) Include both: short `text` (1-2 sentences) + full `detail` (complete extraction)

**Answer:**
chnage the scope of work written language more in contractual terms
---

### Q15: Session Scope — Per Project or Per Project+Trade?

Our backend creates sessions keyed by `{project_id}_{trade}`. The UI shows one workspace per project (all trades visible). Should sessions be:

- (a) Per project+trade (current — separate session per trade)
- (b) Per project (one session holds all trades' results)
- (c) Per project with sub-sessions per trade

Option (b) would require restructuring the session model to hold multiple trade results.

**Answer:**
option b
---

## How to Answer

1. Write your answer after each `**Answer:**` line
2. If none of the options fit, write your own answer
3. For questions where you're unsure, write "Ask [person name]" and I'll flag it
4. Once all answered, share this file back and I'll start implementing the fixes

**Estimated effort after answers:**
- P0 fixes (Q1, Q2, Q5): ~7 hours
- P1 fixes (Q3, Q4, Q8): ~7 hours
- P2 fixes (Q6-Q15): ~5 hours
- **Total: ~19 hours** (will reduce based on answers — many gaps may not apply)
