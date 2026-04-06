# Multi-Agent Scope Gap Architecture — Brainstorm & Clarifying Questions

**Date:** 2026-04-05
**Status:** BRAINSTORMING — Awaiting user answers before design
**Author:** Claude (Opus 4.6)

---

## Table of Contents

1. [Current System Understanding](#1-current-system-understanding)
2. [Claude Web Chat Analysis](#2-claude-web-chat-analysis)
3. [JSX Prototype Analysis](#3-jsx-prototype-analysis)
4. [Competitor Comparison (ScoreboardAI vs iFieldSmart)](#4-competitor-comparison)
5. [Demo Video Summary](#5-demo-video-summary)
6. [User's Vision (Synthesized)](#6-users-vision-synthesized)
7. [Answered Questions (from user + chat context)](#7-answered-questions)
8. [Remaining Clarifying Questions](#8-remaining-clarifying-questions)

---

## 1. Current System Understanding

### 1.1 Construction Intelligence Agent — Current Architecture

**Location:** `PROD_SETUP/construction-intelligence-agent/`
**Stack:** FastAPI + OpenAI (gpt-4.1-mini) + MongoDB HTTP APIs + Redis + python-docx
**Port:** 8003, behind Nginx reverse proxy at `https://ai5.ifieldsmart.com/construction/`

#### Current 3-Agent Pipeline (Single-Pass)

```
User Query → IntentAgent → DataAgent → GenerationAgent → Word Doc
```

| Agent | Role | Key Behavior |
|-------|------|-------------|
| **IntentAgent** | Detects trade, document type, intent | Hybrid: keyword (<1ms) + LLM fallback |
| **DataAgent** | Fetches drawing data, builds context | Parallel pagination (15 concurrent), token-budget compression |
| **GenerationAgent** | Master orchestrator (7 phases) | Parallel phase execution via asyncio.gather() |

#### Current 7-Phase Execution

| Phase | What Happens | Latency |
|-------|-------------|---------|
| 1 | Session load + cache check + metadata (parallel) | ~50ms |
| 2 | Keyword intent + context build + full intent (parallel) | ~200ms + API fetch |
| 3 | Trade validation (rebuild if intent changed) | ~0ms or ~200ms |
| 4 | LLM generation (gpt-4.1-mini, 120k context) | ~2-4 min (large) |
| 5 | Hallucination guard (groundedness scoring) | ~50ms |
| 6 | Word doc generation (in thread pool) | ~100-500ms |
| 7 | Persist (cache + session + tokens) | ~50ms |

**Total:** ~4 min (large, 11k records) | ~2 min (medium) | <500ms (cached)

#### Current Limitations (Observed)

1. **Single-pass generation** — No verification loop; hallucination guard is informational only
2. **Single trade per request** — Can only process one trade at a time
3. **No cross-trade gap detection** — Cannot identify ambiguous scope items
4. **No completeness tracking** — No mechanism to measure extraction coverage
5. **No multi-agent verification** — Single LLM call, no review/validation by secondary agents
6. **No source traceability** — LLM output doesn't link items to specific drawings
7. **No PDF upload/processing** — Works from pre-indexed MongoDB data, not raw PDFs
8. **No template/preset system** — Every request starts from scratch

---

## 2. Claude Web Chat Analysis

### What Was Discussed (from claude_chat_requirements.md)

The user shared 3 demo videos of ScoreboardAI and a detailed product analysis document to Claude web. The conversation resulted in a React prototype (`ifieldsmart-scope-ai.jsx`) that replicates and extends ScoreboardAI's features.

### Key Requirements Extracted from Chat

1. **"Create a similar PRODUCT for me for iFieldSmart.ai"** — Full product, not just a feature
2. **"I have contract drawings and specification with me that I will upload"** — PDF upload-based workflow
3. **"Use your brain as a construction scope intelligence expert as well as scope contract creation agent"** — Domain expertise required
4. **"Use multi agent approach to do this task"** — Explicit multi-agent requirement
5. **"Give me the complete Functional UI/UX to test this product"** — Working frontend needed
6. **"It should show me the source of assignment on the drawing — it should highlight the text on drawing"** — Source traceability with visual highlighting
7. **"Scope of work export with reference drawings on that the text is highlighted"** — Export must include highlighted drawing references

### What Claude Web Built (5 AI Agents)

| # | Agent | Role |
|---|-------|------|
| 1 | **Spec Parser Agent** | Parse PDFs, identify CSI MasterFormat sections |
| 2 | **Scope Extractor Agent** | Pull scope inclusions from specs and drawings |
| 3 | **Trade Classifier Agent** | Map extracted items to trade packages |
| 4 | **Ambiguity Detector Agent** | Flag overlapping/unclear scope assignments |
| 5 | **Gotcha Scanner Agent** | Catch hidden costs, gaps, coordination issues |

### 8 Pages Built in Prototype

1. **Dashboard** — Project overview, stats, trade breakdown, agent status
2. **Upload Documents** — Drag-and-drop PDFs, tag as Drawing or Spec
3. **Trade Packages** — Define trades with CSI codes, colors (18 preloaded trades)
4. **Scope Review** — Checklist with trade filtering, confidence scores, source tracing
5. **Ambiguity Resolution** — AI recommendations for overlapping scopes
6. **Gotcha Scanner** — Proactive risk detection (beyond ScoreboardAI)
7. **Scopes Map** — CSI Division tree showing trade-to-code mappings
8. **Export** — Per-trade CSV export with source traceability

---

## 3. JSX Prototype Analysis (ifieldsmart-scope-ai.jsx)

### What the Prototype Actually Implements (1220 lines)

**Working Features:**
- PDF upload with drag-and-drop
- PDF.js text extraction (page-by-page)
- Claude Sonnet API for scope extraction (real, not simulated)
- Claude Sonnet API for ambiguity detection (second API call)
- 4-step workflow: Upload → Trade Setup → AI Processing → Review & Export
- DrawingViewer with PDF.js canvas rendering + trade-colored text highlighting
- "Draw a Highlight" button for manual highlight drawing on PDF
- Highlight Properties Panel (trade dropdown with search, text, critical checkbox, comments)
- Right-click context menu on highlights (Properties, CSI Codes, Delete)
- ScopeReport per trade with source drawing references
- CSV export (per-trade and all trades)
- 3-tab sidebar: Drawings | Specs | Findings
- Findings sidebar with page-level finding counts + badges
- 18 preloaded trades with CSI code mappings

**Architecture Pattern:**
```
Upload PDFs
  → PDF.js extracts text per page
  → Claude Sonnet API extracts scope items (structured JSON)
  → Claude Sonnet API detects ambiguities
  → Results displayed in React UI
  → Click any scope item → PDF viewer highlights source text on drawing
```

**Key Technical Details:**
- Uses Claude API directly from frontend (no backend proxy — security concern for production)
- ArrayBuffer management with `.slice(0)` to prevent detachment
- PDF text layer coordinates used for highlight positioning
- Semantic snippet matching for finding source locations on drawings

### What the Prototype Does NOT Implement

1. **No backpropagation loop** — Single-pass extraction only
2. **No completeness tracking** — No % coverage metric
3. **No backend integration** — Everything runs client-side
4. **No persistence** — Refresh = lost data
5. **No user auth** — No login/session management
6. **No multi-project support** — Single project at a time
7. **No Word doc generation** — CSV only
8. **No integration with existing MongoDB drawing data** — Only uploaded PDFs
9. **No Gotcha Scanner** — Listed in UI but not implemented
10. **No Scopes Map** — Listed in UI but not implemented

---

## 4. Competitor Comparison

### ScoreboardAI vs Current iFieldSmart vs Target Product

| Feature | ScoreboardAI | iFieldSmart (Current) | JSX Prototype | Target Product |
|---------|-------------|----------------------|---------------|---------------|
| **Input Method** | PDF upload | MongoDB pre-indexed drawings | PDF upload | Both: MongoDB + PDF upload |
| **Scope Extraction** | Proprietary ML + LLM | OpenAI gpt-4.1-mini (single pass) | Claude Sonnet (single pass) | Multi-agent pipeline (3 passes) |
| **Source Traceability** | Every item → source drawing/spec | None (LLM output only) | Click → PDF viewer with highlights | Item-level with drawing highlights |
| **Ambiguity Resolution** | Explicit detail-by-detail assignment | Not addressed | Claude API detection | Dedicated Ambiguity Agent |
| **Trade Management** | Import from past projects | Keyword-based (5 trades) | 18 preloaded trades | Full trade management + templates |
| **Output Format** | Per-trade scope inclusions export | Word document (.docx) | CSV export | Word + PDF + CSV + JSON |
| **Drawing Viewer** | Inline PDF with trade-colored highlights | None | PDF.js with manual highlights | Full drawing viewer with annotations |
| **Completeness Check** | Not visible | None | None | Multi-pass backpropagation (max 3) |
| **Gotcha Detection** | Not visible | None | Listed but not built | Dedicated Gotcha Scanner Agent |
| **Real-time Streaming** | Not visible | SSE streaming | None | SSE streaming per agent phase |
| **Conversation Memory** | Not visible | Session-based with history | None | Session-based with S3 persistence |
| **Multi-project** | Per-project templates | Drawing sets per project | Single project | Multi-project with set filtering |
| **Pricing Model** | Enterprise (sales-led) | Internal product | N/A | Internal product |

### Key Competitive Advantages to Pursue

1. **MongoDB Integration** — ScoreboardAI requires PDF upload; we already have indexed drawing data in MongoDB. Use BOTH sources.
2. **Backpropagation Loop** — Neither ScoreboardAI nor the prototype does multi-pass verification. This is a differentiator.
3. **Streaming Progress** — Real-time SSE showing each agent's progress (no competitor has this).
4. **Gotcha Scanner** — Proactive risk detection is listed as "beyond ScoreboardAI" — must actually build it.
5. **Existing RAG Pipeline** — Cross-project intelligence from our RAG agent.

---

## 5. Demo Video Summary (from user descriptions in Claude chat)

### Video 1: Scope Report + Source Traceability
- Scope inclusions pulled directly from drawings and specs
- Every report item links back to a reference in the drawings or specs
- 3-tab sidebar: Drawings | Specs | Findings
- Findings tab shows each source page with badge count
- Drawing text color-coded by trade on rendered PDF
- Bottom action bar with "Ignore" and "Export" buttons

### Video 2: Ambiguity Resolution + Drawing Highlighting
- "Draw a Highlight" button for manual annotations
- Right-click context menu: SpecConnect, Properties, CSI Codes, Delete
- Highlight Properties Panel: trade dropdown with search, text field, critical checkbox, comments
- Trade/Scope dropdown on toolbar to filter visible highlights
- Filter tags (Div 07 drawing, A744) as dismissible pills

### Video 3: Trade Setup + Configuration
- "Scopes View" showing CSI divisions with trade-to-code mapping (Div 01-33)
- "Save and Run" button (triggers AI extraction after saving trades)
- "Trades changed. Save required." warning banner
- Advanced settings: hex color input + opacity percentage
- Import trade configurations from past projects

---

## 6. User's Vision (Synthesized from ALL Sources)

### The Product: iFieldSmart ScopeAI

A **multi-agent scope intelligence platform** that:

1. Takes construction drawings/specs (from MongoDB or PDF upload)
2. Runs them through **6 specialized agents** (user confirmed: all agents)
3. Uses a **backpropagation loop** (max 3 attempts) for completeness
4. Produces per-trade scope reports with **source traceability to specific drawings**
5. Handles **ambiguous scope** (items between trades like flashing, waterproofing)
6. Detects **gotchas** (hidden costs, coordination issues)
7. Exports as **Word documents with highlighted drawing references**

### Multi-Agent Pipeline (User's Requirement)

```
                    ┌─────── BACKPROPAGATION LOOP (max 3 attempts) ───────┐
                    │                                                      │
Input Data ──→ Extraction ──→ Classification ──→ Ambiguity ──→ Completeness ──→ Quality
   Agent          Agent           Agent           Agent          Agent        Agent
                    │                                                  │      │
                    │    ← Remaining items + targeted corrections ←─────┘      │
                    │                                                          │
                    └──────────────────────────────────────────────────────────┘
                                          │
                                After 3 attempts OR 100% completion
                                          │
                                ┌─────────┴──────────┐
                                │                      │
                           100% done              Partial result
                           → Document Agent       → Show % remaining
                           → Generate export      → Ask user: continue?
```

### User's Answers from the Brainstorm File

| Question | Answer |
|----------|--------|
| Q1: Which agent roles? | **All of them** (Extraction, Classification, Ambiguity, Completeness, Quality, Document) |
| Q4: Backpropagation approach | **Both (b) and (c)** — incremental missing items + targeted corrections to specific agents |
| Q5: Multi-trade processing | **(c) Keep single-trade** — user explicitly chooses trade |

---

## 7. Answered Questions (from Chat Context + User Answers)

These questions from the original brainstorm are now answered:

| # | Question | Answer | Source |
|---|----------|--------|--------|
| Q1 | Agent specialization | All 6 agents (Extraction, Classification, Ambiguity, Completeness, Quality, Document) | User answer in brainstorm file |
| Q2 | Scope gap format | **(c) Both** — Drawing data extraction + structured trade responsibility assignment. The prototype shows structured JSON extraction with trade assignment, AND the chat shows user wants Word doc reports with drawing references. | Claude chat + prototype behavior |
| Q4 | Backpropagation mechanics | **(b) + (c)** — Send missing items incrementally AND target specific agents that missed items | User answer in brainstorm file |
| Q5 | Multi-trade processing | **(c) Single-trade** — user explicitly chooses | User answer in brainstorm file |
| Q11 | User persona | **Preconstruction Manager** — Creates bid packages, needs scope inclusions per trade for distribution to subcontractors | Claude chat: "scope contract creation agent" + trade package workflow |
| Q13 | Demo videos content | Described above in Section 5 | Claude chat: user described all 3 videos |
| Q14 | Claude chat content | Full analysis in Sections 2-3 | Read from claude_chat_requirements.md |

---

## 8. Remaining Clarifying Questions

### CRITICAL (Must Answer Before Design)

**Q3. What does "100% extraction" mean concretely?**

From the prototype, I can see that extraction means: "every scope item from every page of the drawing text." The backpropagation loop checks completeness. But how do we MEASURE completeness?

Proposed definition (confirm or correct):
- **Drawing coverage:** Every drawing name in the API response appears in the output (measurable — compare API drawing list vs. output references)
- **No hallucinations:** Every item in the output can be traced to source data (measurable — cross-reference)
- **CSI coverage:** Every CSI division present in the source data is represented in the output

**Is this the right definition? Or do you have a different one?**

**Answer** : Yes it is correct

---

**Q6. Source traceability — how granular?**

The prototype implements item-level traceability (each scope item links to a specific page + source snippet). ScoreboardAI does the same.

Options:
- (a) **Drawing-level** — Each section cites which drawing(s) it came from
- (b) **Item-level** — Each scope item links to the specific drawing record (prototype does this)
- (c) **Page-level** — Link to specific PDF page with highlighted text on the drawing

**The prototype does (b) + (c). Should the backend also support this?** This means the LLM must output structured JSON with page numbers and source snippets for EVERY item, not free-form markdown.

**Answer** : Yes

---

### IMPORTANT (Affects Architecture)

**Q7. Template/preset system — is this needed for v1?**

ScoreboardAI has it. The prototype has 18 preloaded trades but no save/import. Video 3 shows "import from past projects."

- (a) Yes, build into v1
- (b) No, defer to v2
- (c) Simple preset system (save/load trade configs per project)

**Answer** : option b.

---

**Q8. What is the acceptable latency?**

Current single-pass: ~4 min for large datasets.
Multi-agent with backpropagation will be significantly longer.

**What is the max acceptable wall-clock time for a single-trade report?**
- (a) Under 5 minutes (aggressive — requires heavy parallelization)
- (b) Under 10 minutes (feasible with smart incremental passes)
- (c) Under 15 minutes (comfortable — allows thorough multi-pass)
- (d) Background job — user submits and comes back later (no limit)

**Answer** : under 5 minutes

---

**Q9. LLM model choice**

Current backend: `gpt-4.1-mini` ($0.40/$1.60 per 1M tokens)
Prototype frontend: `claude-sonnet` (via Anthropic API)

For the multi-agent backend:
- (a) Keep gpt-4.1-mini for all agents (cheapest)
- (b) Use gpt-4.1 (full) for extraction, mini for validation (balanced)
- (c) Use Claude Sonnet for extraction (as prototype does), gpt-4.1-mini for validation
- (d) Allow configurable model per agent

**Answer** : Use Latest GPT such as GPT 5 or relative who has minimum latency and highest accuracy output.

---

**Q10. Background job vs blocking?**

- (a) Blocking with SSE streaming (user sees real-time progress per agent)
- (b) Background job (user submits, gets job ID, polls/downloads later)
- (c) Hybrid (small requests block, large requests auto-background)

**Answer** : Hybrid

---

### SCOPE & PRIORITY

**Q12. What is the output format?**

Current backend: Word document (.docx)
Prototype: CSV only
ScoreboardAI: Per-trade export with source references

Options:
- (a) Word document only (current)
- (b) Word + PDF
- (c) Word + PDF + CSV + structured JSON
- (d) Word + PDF + CSV + JSON + interactive web report

**Answer** : option d

---

**Q15. What is the MVP vs Full Vision?**

| Feature | Priority? |
|---------|-----------|
| Multi-agent extraction pipeline (6 agents) | MVP |
| Backpropagation loop (3 attempts) | MVP |
| Completeness tracking (% done) | MVP |
| Source traceability (drawing references per item) | MVP |
| Ambiguous scope detection + resolution | MVP |
| Gotcha Scanner (hidden costs/risks) | MVP |
| Drawing Viewer with highlights (React frontend) | It is taken care by fronend developers, no need to develop |
| "Draw a Highlight" manual annotation | MVP |
| Template/preset system | MVP |
| PDF upload workflow (in addition to MongoDB) | MVP |
| Background job queue | MVP |
| All 12-point review criteria (scaling, security, etc.) | MVP |

**Please mark each as: MVP / V2 / V3 / NOT NEEDED**

**Answer** : Yes done.

---

## Next Steps

Once the remaining questions (Q3, Q6-Q10, Q12, Q15) are answered, I will:

1. **Propose 2-3 architectural approaches** with trade-offs
2. **Present the detailed design** section by section for approval
3. **Write the final spec** and get sign-off
4. **Create the implementation plan** via the writing-plans skill
5. **Begin development** using parallel agents, TDD, and the full review pipeline



---

*This document will be updated with answers and will evolve into the final design spec.*
