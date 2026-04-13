# Clarifying Questions — Construction Intelligence Agent Enhancements

**Date:** 2026-04-13  
**Features:** S3 Document Persistence, Document Listing, Source Reference `text` Field

---

## Architecture Context (What Already Exists)

Before the questions, here's what I found in the current codebase:

| Area | Current State |
|------|--------------|
| **S3 storage** | Active. Path: `construction-intelligence-agent/generated_documents/{ProjectName}_{ProjectID}/{Trade}/{filename}.docx` |
| **Document listing** | `GET /api/documents/list` exists with `project_id` and `trade` filters — parses S3 folder structure |
| **Document download** | `GET /api/documents/{file_id}/download` — 307 redirect to S3 presigned URL (1hr expiry) |
| **Source references** | `SourceReference` dataclass has: `drawing_id`, `drawing_name`, `drawing_title`, `s3_url`, `pdf_name`, `x`, `y`, `width`, `height` — **no `text` field** |
| **Set handling** | `set_ids` is optional on `ChatRequest`. When provided, uses `summaryByTradeAndSet` API. `set_names` are extracted from API response |
| **Document generation** | Saves to S3 via temp file → upload → delete temp. Filename: `{type}_{trade}_{set_slug}_{project_slug}_{id}_{uuid[:8]}.docx` |

---

## Q1: S3 Folder Structure — SetName When No Set Is Provided

Your requested structure:
```
construction-intelligence-agent/
  └── generated_documents/
      └── ProjectName(projectID)/
          └── SetName/
              └── TradeName/
                  └── generated_doc.docx
```

Currently, `set_ids` is **optional**. A user can query without specifying any set (meaning "all sets for this trade").

**When no `set_ids` are provided**, what should the SetName folder be?

- **(A)** Use a default folder like `All_Sets/`
- **(B)** Make `set_ids` mandatory for document generation going forward
- **(C)** Derive the set from the API response data (use dominant/first set found in records)
- **(D)** Other — please specify

**Answer**: Make `set_ids` mandatory for document generation going forward

**When multiple `set_ids` are provided** (e.g., `[4730, 4731]`), should:

- **(i)** One combined document go into a folder like `Set_4730_Set_4731/` or `Set_4730_4731/`
- **(ii)** Separate documents be generated per set, each in its own set folder

**Answer**: Separate documents be generated per set, each in its own set folder
---

## Q2: SetName Resolution — Where Does the Set Name Come From?

The current API returns `set_id` (integer) in records. The system extracts `set_names` from the response data (e.g., `"Set 4730"`).

- **(A)** Is there a human-readable set name (e.g., `"Foundation Plans"`, `"Electrical Sheets"`) available from the API or SQL database? If so, which field/table?
- **(B)** Should we just use the set_id as the folder name (e.g., `Set_4730/`)?
- **(C)** Is there a separate API endpoint or SQL query to look up set names?

**Answer**: It is human readable set name

---

## Q3: The `text` Field in Source References — What Exactly Is It?

You want to add a `text` parameter to `source_references` for highlighting in reference drawing PDFs. The current schema:

```json
{
  "A-12": {
    "drawing_id": 12345,
    "drawing_name": "A-12",
    "drawing_title": "ELECTRICAL FLOOR PLAN",
    "s3_url": "...",
    "pdf_name": "pdfA12",
    "x": 100, "y": 200, "width": 50, "height": 30
  }
}
```

What is the `text` field?

- **(A)** The actual text content extracted from that drawing at those coordinates (the `text` field from the `DrawingRecord` API response — the note/annotation content)
- **(B)** A label/summary describing what should be highlighted (e.g., `"Panel Schedule EP-1"`)
- **(C)** The specific text snippet from the LLM answer that references this drawing (the citation text)
- **(D)** Something else — please describe

**Follow-up:** Should there be **one text per drawing reference**, or could a single drawing have **multiple text regions** with different coordinates? Currently, each drawing appears once in `source_references` (keyed by `drawing_name`). If multiple text regions exist per drawing, the schema would need to change to support an array.


**Answer**: The actual text content extracted from that drawing at those coordinates (the `text` field from the `DrawingRecord` API response — the note/annotation content). It should be single "text" parameter.



---

## Q4: Coordinates and Text Relationship

Currently, coordinates (`x`, `y`, `width`, `height`) can be `null` for some drawings. 

- **(A)** Should the `text` field also be `null` when coordinates are `null`? (i.e., they're always paired)
- **(B)** Can `text` exist independently of coordinates? (e.g., text extracted but no bounding box available)
- **(C)** Are the coordinates in **pixel units** (as current schema suggests) or **normalized [0,1] coordinates** relative to PDF page dimensions?


**Answer**:  the coordinates are in **pixel units** (as current schema suggests) or **normalized [0,1] coordinates** relative to PDF page dimensions

---

## Q5: Document Persistence on Page Refresh — Root Cause

You mentioned: *"once the page is refreshed, the generated document gets deleted and need to generate again."*

From the backend, documents **are** being saved to S3 and the listing API works. So the issue seems to be on the **frontend side** — the UI loses the document reference after refresh.

- **(A)** Is the frontend a **React/Vue/Angular SPA** that stores the document reference in component state (lost on refresh)?
- **(B)** Is the frontend the **Streamlit scope-gap-ui** in this repo?
- **(C)** Is it an **external frontend** (e.g., iFieldSmart platform) that calls these APIs?
- **(D)** Should we solve this purely on the **backend** by providing a "get latest document for project/set/trade" API, so the frontend can always recover the reference?

**Answer**: if backend functionality is working fine to store the document then it should be front problem. It is developed in Angular so give me step or direction to store the component on frontend once it generated.

---

## Q6: Document Naming Convention

Your requested structure shows `generated_doc.docx` as the filename. Currently, files are named with rich metadata:
```
scope_electrical_set4730_GranvilleHotel_7298_a1b2c3d4.docx
```

- **(A)** Keep the current descriptive naming (recommended — avoids overwrites, enables versioning)
- **(B)** Switch to a simple `generated_doc.docx` per folder (only one document per Project/Set/Trade combination)
- **(C)** Use a hybrid: descriptive name, but also maintain a `latest.docx` symlink/copy

**Answer**: Keep the current descriptive naming

---

## Q7: Document Versioning — Overwrite or Accumulate?

If a user regenerates a document for the **same Project + Set + Trade** combination:

- **(A)** **Overwrite** the previous document (saves storage, always shows latest)
- **(B)** **Keep all versions** with timestamps (enables history, but consumes more storage)
- **(C)** **Keep last N versions** (e.g., last 3) and auto-delete older ones

**Answer**: **Overwrite** the previous document (saves storage, always shows latest)

---

## Q8: Document Listing API — Flat vs Hierarchical

The existing `GET /api/documents/list` returns a **flat list** with metadata. You want to *"manage and display the generated documents same as the folder structure"*.

- **(A)** Return a **tree/hierarchical** JSON response:
  ```json
  {
    "projects": {
      "GranvilleHotel(7298)": {
        "sets": {
          "Set_4730": {
            "trades": {
              "Electrical": [{ "filename": "...", "download_url": "..." }],
              "Plumbing": [...]
            }
          }
        }
      }
    }
  }
  ```
- **(B)** Keep the **flat list** but add `set_name` as a filter parameter and include it in each document's metadata
- **(C)** Provide **both**: flat list endpoint (existing) + a new tree endpoint for the UI

**Answer**: Keep the **flat list** but add `set_name` as a filter parameter and include it in each document's metadata

---

## Q9: Document Listing Scope — Per-Project or Global?

When listing documents:

- **(A)** Always require a `project_id` (show documents only for the current project)
- **(B)** Allow global listing across all projects (admin view)
- **(C)** Support both — `project_id` optional, returns all if omitted

**Answer**: Always require a `project_id` (show documents only for the current project)

---

## Q10: Backward Compatibility — API Response Changes

Adding `text` to `source_references` changes the API response schema. The existing consumers (frontend, integrations) receive the current schema.

- **(A)** **Additive only** — just add `text` field to existing schema. Existing consumers ignore unknown fields (safe)
- **(B)** **Version the API** — add `/api/v2/chat` with new schema, keep `/api/chat` unchanged
- **(C)** **Replace in place** — modify existing endpoint, update all consumers simultaneously

My recommendation: **(A)** — additive change is backward-compatible and simplest.

**Answer**:  **(A)** — additive change is backward-compatible and simplest.

---

## Q11: Where Does `text` Data Come From in the Pipeline?

The `SourceIndexBuilder.build()` extracts source references from raw API records. The API records already contain a `text` field (`DrawingRecord.text`).

- **(A)** Should we use the `DrawingRecord.text` field directly as the `text` in source references? (This is the full note/annotation text from the drawing)
- **(B)** Should we extract only the portion of text that the LLM actually cited in its answer?
- **(C)** Should we use the `source_snippet` field from scope pipeline's `ScopeItem` model?
- **(D)** Some other source — please specify

**Answer**: use the `DrawingRecord.text` field directly as the `text` in source references

---

## Q12: Multiple Text Entries Per Drawing

Currently, `source_references` is keyed by `drawing_name` (one entry per drawing). But a single drawing can have **many text records** (different notes at different coordinates).

When a drawing has multiple relevant text items:

- **(A)** Include **only the most relevant** text item (highest confidence/relevance score)
- **(B)** Change the schema to support **an array of text+coordinate pairs** per drawing:
  ```json
  {
    "A-12": {
      "drawing_id": 12345,
      "drawing_name": "A-12",
      "drawing_title": "ELECTRICAL FLOOR PLAN",
      "s3_url": "...",
      "pdf_name": "pdfA12",
      "annotations": [
        { "text": "Panel EP-1, 200A, 3-phase", "x": 100, "y": 200, "width": 50, "height": 30 },
        { "text": "Conduit run to MDP", "x": 300, "y": 150, "width": 40, "height": 20 }
      ]
    }
  }
  ```
- **(C)** Flatten into multiple entries with unique keys (e.g., `A-12_1`, `A-12_2`)

**Answer**: **(B)** Change the schema to support **an array of text+coordinate pairs** per drawing

---

## Q13: Frontend Document Listing — Who Builds the UI?

You mentioned displaying documents in a hierarchical structure. 

- **(A)** Should I build/update the **Streamlit scope-gap-ui** in this repo to show the document tree?
- **(B)** Is there an **external frontend** that will consume the API? (I only build the backend API)
- **(C)** Should I create a **new simple HTML/JS page** for document browsing?


**Answer**: there is an **external frontend** that will consume the API

---

## Q14: Sandbox Deployment — Testing Scope

For sandbox VM (54.197.189.113) deployment:

- **(A)** Deploy **only the construction-intelligence-agent** with the new changes
- **(B)** Deploy the **full VCS stack** (all agents, gateway, etc.)
- **(C)** Should sandbox use the **same S3 bucket** (`agentic-ai-production`) or a separate sandbox bucket?
- **(D)** Should sandbox use the **same MongoDB API** endpoints or different ones?

**Answer**:  Deploy **only the construction-intelligence-agent** with the new changes. sandbox use the **same S3 bucket**. sandbox use the **same MongoDB API** endpoints

---

## Q15: Excel Sheet Update — What Format?

You want updates in `Attendance_Aniruddha.xlsx` sheet `"Xtra-work-april"`.

- **(A)** What columns does this sheet have? (e.g., Date, Task, Hours, Status, Notes?)
- **(B)** Should I add one row per feature (3 rows: S3 persistence, document listing, text field) or one combined row?
- **(C)** What date should I use — today (2026-04-13) or a range?

**Answer**: Just add it in the nex rows, apply the same structure.


---

## Summary of Questions

| # | Topic | Key Decision |
|---|-------|-------------|
| Q1 | SetName when no set_ids | Default folder naming |
| Q2 | SetName resolution | Where to get human-readable set names |
| Q3 | `text` field definition | What data goes in the text field |
| Q4 | Coordinates + text relationship | Null handling, coordinate units |
| Q5 | Refresh persistence | Frontend vs backend issue |
| Q6 | Document naming | Descriptive vs simple filename |
| Q7 | Document versioning | Overwrite vs accumulate |
| Q8 | Listing API format | Flat vs hierarchical response |
| Q9 | Listing scope | Per-project vs global |
| Q10 | Backward compatibility | Additive vs versioned API |
| Q11 | Text data source | Which field to use for `text` |
| Q12 | Multiple texts per drawing | Single vs array schema |
| Q13 | Frontend UI | Who builds the document listing UI |
| Q14 | Sandbox scope | What to deploy and which resources |
| Q15 | Excel format | Sheet columns and row format |

**Please answer each question (even briefly) so I can proceed with a precise design.**
