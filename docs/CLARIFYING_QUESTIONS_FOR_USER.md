# Clarifying Questions — Scope Gap UI Integration

**Date:** 2026-04-06
**Context:** Follow-up questions based on user's answers to the 15 clarifying questions in `SCOPE_GAP_CLARIFYING_QUESTIONS (2).md`
**Status:** AWAITING ANSWERS — Answer inline after each `**Answer:**` line, then share back

---

## Summary of Your Previous Answers

| # | Topic | Your Answer | What It Means |
|---|-------|-------------|---------------|
| Q1 | Drawing/Spec source | Separate API endpoint (c) | Need new API integration for drawing index |
| Q2 | Revisions/Sets | Hardcoded per project (c) | Frontend owns the revision list |
| Q3 | Drawing Viewer | External viewer component (c) | Backend does NOT need x/y annotation coords |
| Q4 | Highlight Persistence | MVP — needed for launch (a) | Must build highlight save/load endpoint |
| Q5 | Multi-Trade | Auto-run all trades on open (b) | Parallel pipeline for ALL trades simultaneously |
| Q6 | Trade Colors | Backend owns palette (a) | Add color mapping to API response |
| Q7 | Checkbox State | Client-side only (b) | No backend change needed |
| Q8 | Reference Panel | Multiple drawing_refs per item (a) | Extend ScopeItem model with `drawing_refs: list[str]` |
| Q9 | Export Format | Word + PDF (b) | Remove CSV/JSON from export UI |
| Q10 | Findings Count | From pipeline result (a) | Group-by counting on `drawing_name` |
| Q11 | Pipeline Trigger | Auto on open + pre-computed (b+d) | Background pre-computation on project creation |
| Q12 | Drawing Viewer checkboxes | Visual toggle only (a) | No persistence needed |
| Q13 | 23 Trades | Dynamic from MongoDB data (c) | Add trades discovery endpoint per project |
| Q14 | Scope Item Text | Contractual language | Change LLM prompt to output contractual terms |
| Q15 | Session Scope | Per project (b) | Restructure session model — one session holds ALL trades |

---

## Follow-Up Questions

### FQ1: Drawing/Spec Source API (relates to Q1)

You said there's a **separate API endpoint** for drawing sets/sheets.

- (a) What is the exact API URL/path? (e.g., `GET /api/drawings/list?projectId={id}`)
- (b) What does the response look like? (fields like `drawingName`, `category`, `setTrade`, etc.)
- (c) Is this an **existing** iFieldSmart API that's already live, or does it need to be built?
- (d) Does it return the categorized tree structure (GENERAL, ELECTRICAL, MECHANICAL, etc.) or do we derive categories from a field?

**Answer:** Existing api that is already inn use


---

### FQ2: External Drawing Viewer (relates to Q3)

You chose an external drawing viewer component. We need to know:

- (a) Which viewer? (e.g., Autodesk Forge/APS, OpenSeaDragon, PDF.js with custom layer, or a proprietary iFieldSmart viewer)
- (b) Does the viewer have an API for programmatic annotation overlays? (needed for highlight persistence in Q4)
- (c) How does the viewer receive drawing data — by URL (S3 link), by file upload, or via an SDK call?
- (d) Is the viewer already integrated in the iFieldSmart web app, or is this new?

**Answer:** already integrated


---

### FQ3: Highlight Persistence Storage (relates to Q4)

You said highlights are MVP. We need to decide where to store them:

- (a) Store in Redis (fast, but lost on restart unless backed by persistence)
- (b) Store in MongoDB via an iFieldSmart API (durable, but needs a new collection/endpoint)
- (c) Store in S3 as JSON files per project/drawing (durable, cheap, simple)
- (d) Store in the scope gap session (ties highlights to a specific pipeline run)

Also:
- (e) Are highlights **per-user** (each user sees their own) or **shared** (all users on a project see the same highlights)?
- (f) What data does a highlight contain? Just a rectangle region (x, y, width, height) on a drawing page, or more (color, label, linked scope item)?

**Answer:** It should be saved in s3 in json and highlights should be **per-user**. Highligh contain all of it mention in th eoption


---

### FQ4: Auto-Run All Trades — Scale & Cost (relates to Q5 + Q11)

You want the pipeline to auto-run ALL trades when the user opens the Scope Workspace, AND pre-compute on project creation. This has major implications:

- (a) How many trades does a typical project have? (3-5? 10-15? all 23?)
**Answer:** Each project have around 50 to 150 trades
- (b) Each trade pipeline run costs ~$0.05-0.15 in OpenAI tokens. Running all trades for a project could cost $0.50-3.00+ per run. Is that acceptable?
**Answer:** acceptable
- (c) For pre-computation (Q11 answer "d"): what triggers "project creation"? Is there a webhook/event from iFieldSmart, or do we poll for new projects?
**Answer:** webhook/event from iFieldSmart
- (d) Should pre-computation run once (on creation) or also re-run when new drawings are uploaded to the project?
**Answer:** Also re-run when new drawings are uploaded to the project
- (e) If a project has 15 trades and 11,000+ records, the full run could take 15-30 minutes. Should we show partial results as each trade completes, or wait for all?
**Answer:** partial results as each trade completes.




---

### FQ5: Per-Project Session Restructure (relates to Q15)

You want ONE session per project (holding ALL trades). This is a significant architecture change:

- (a) Current session key: `{project_id}_{trade}`. New key would be just `{project_id}`. Should old per-trade sessions be migrated or discarded?

**Answer:** migrated

- (b) The session will hold results from potentially 15+ trade runs. Should we store each trade's result as a nested object within the session, or keep trade results separate but linked by a parent session ID?

**Answer:** keep trade results separate but linked by a parent session ID

- (c) When the user re-runs a single trade, should it replace that trade's results in the session, or keep both (version history)?

**Answer:** keep both

- (d) Session size could grow significantly (15 trades × full pipeline results). Should we set a max session size and archive older runs?

**Answer:** archive older runs


---

### FQ6: Contractual Language Style (relates to Q14)

You want scope items written in "contractual terms." To tune the LLM prompt correctly:

- (a) Can you share 2-3 example sentences of the contractual style you expect? (e.g., "Contractor shall furnish and install..." vs "Install panel LP-1 per drawing E-101")

**Answer:** You can consider on your own

- (b) Should the language include standard construction contract phrases like "furnish and install", "coordinate with", "provide allowance for", "verify in field"?

**Answer:** Yes

- (c) Should items reference specific contract divisions (e.g., "per Division 26 — Electrical")?

**Answer:** Yes

- (d) Is there a reference document or existing scope of work that demonstrates the desired tone?

**Answer:** Yes


---

### FQ7: Hardcoded Revisions (relates to Q2)

You said revisions are "hardcoded per project in the main app." For the scope gap UI:

- (a) Does the frontend already know which revision/set to use, and just passes the `set_id` to us?

**Answer:** Yes

- (b) Or do we need to provide a list of available sets so the frontend can show the dropdown?

**Answer:** YEs

- (c) If the user doesn't select a revision, should we default to the latest/most recent set, or process ALL sets?

**Answer:** Yes


---

### FQ8: Trade Colors — Backend Palette (relates to Q6)

You want the backend to own the trade color palette.

- (a) Should we use the exact 23 colors from the current UI (`scopegap-agent-v3.html`), or is there an official iFieldSmart brand color palette for trades?

**Answer:** Yes

- (b) If a new trade appears (not in the 23), should we auto-generate a color (e.g., hash-based) or return a default?

**Answer:** Yes

- (c) Should the color be returned as hex (#F48FB1), RGB, or both?

**Answer:** Yes


---

### FQ9: Export — Word + PDF Details (relates to Q9)

You chose Word + PDF only.

- (a) Should the PDF be a direct conversion of the Word doc (same content, same styling)?

**Answer:** Yes

- (b) Or should the PDF have a different layout (e.g., more compact, landscape tables)?

**Answer:** No as it is same

- (c) Should exported documents include ALL trades in one file, or one file per trade?

**Answer:** Yes

- (d) The current pipeline generates per-trade documents. For the "Export All" button, should we generate a single combined document or a ZIP of per-trade files?

**Answer:** Yes


---

### FQ10: Dynamic Trades Discovery (relates to Q13)

You want trades fetched dynamically from MongoDB per project.

- (a) Is there an existing API that returns the list of trades for a project? (e.g., `GET /api/trades?projectId={id}`)

**Answer:** There are two apis one is from project_id/trade and project_id/setid/trade

- (b) Or should we derive trades from the `summaryByTrade` response (extract unique `setTrade` values)?

**Answer:** Maintain it accordingly

- (c) Should we cache the trades list per project? If so, for how long? (trades rarely change within a project)

**Answer:** Yes, as the session continues


---

## How to Answer

1. Write your answer after each `**Answer:**` line
2. If none of the options fit, write your own answer
3. For questions where you're unsure, write "TBD" or "Ask [person]"
4. Once all answered, share this file back and I'll proceed with the design

---

## What Happens Next

After you answer these questions, I will:
1. Create a detailed design document covering all 12 evaluation perspectives (scaling, optimization, performance, security, compliance, etc.)
2. Review the complete infrastructure architecture
3. Get your final confirmation before starting phase-wise development
4. Develop, test, and deploy to sandbox VM
5. Push to GitHub
