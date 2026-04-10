# Export Document Redesign — Clarifying Questions

Answer each question to finalize the design. Pick an option or write your own.

---

## Q1: Scope Item Format in Exported Documents

Currently each item shows:
```
Contractor shall furnish and install 8" concrete foundation...
  CSI: 03 30 00 | Confidence: 50% | Source: "FOUND-8 8" CONCRETE FOUNDATION..."
```

**Which format do you want in exports?**

- **A) Clean text only** — just the scope item text grouped by drawing, no metadata at all
  ```
  A-23
  • Contractor shall furnish and install 8" concrete foundation with #4 bars...
  • Contractor shall furnish and install 12" concrete foundation wall, f'c=3000 PSI...
  ```

- **B) Keep CSI code, remove confidence + source**
  ```
  A-23
  • [CSI 03 30 00] Contractor shall furnish and install 8" concrete foundation...
  ```

- **C) Something else** — describe what you want

**Your answer:** Clean text only

---

## Q2: What Should the Exported Document Header Look Like?

Currently:
```
SCOPE GAP REPORT
Project:  (ID: 7276)
Trade: Concrete
Generated: 2026-04-07 11:33 UTC
Completeness: 70.7%
```

You want to add project name and remove completeness. **Which header format?**

- **A) Clean professional header**
  ```
  SCOPE OF WORK — CONCRETE
  Project: SINGH RESIDENCE (ID: 7276)
  Location: Nashville, TN
  Date: April 7, 2026
  ```

- **B) Minimal header**
  ```
  SINGH RESIDENCE — Concrete Scope of Work
  Project ID: 7276 | Generated: April 7, 2026
  ```

- **C) Something else** — describe what you want

**Your answer:** Clean professional header

---

## Q3: Should the Executive Summary Stay or Go?

Currently: `"This report contains 53 scope items, 5 ambiguities, and 10 gotchas."`

Since ambiguities and gotchas are being removed from the export, what should happen?

- **A) Remove the executive summary entirely** — jump straight to scope items
- **B) Simplify it** — `"This report contains 53 scope items across 13 drawings."`
- **C) Keep as-is but remove ambiguity/gotcha counts** — `"This report contains 53 scope items."`

**Your answer:** Remove the executive summary entirely — jump straight to scope items

---

## Q4: S3 Reference Document Links — What Format?

You want to use S3 bucket path + pdfName to link to source drawings. **How should these appear?**

- **A) Hyperlinks on drawing names** — clicking "A-23" in the document opens the PDF
  ```
  A-23  ← clickable link to S3 presigned URL
  • Contractor shall furnish and install...
  ```

- **B) Reference table at the end** — a table listing all referenced drawings with their S3 links
  ```
  REFERENCE DRAWINGS
  | Drawing | Link |
  | A-23    | https://s3.amazonaws.com/...A-23.pdf |
  | A-19    | https://s3.amazonaws.com/...A-19.pdf |
  ```

- **C) Both** — clickable drawing headings + reference table at the end

- **D) Something else** — describe

**Your answer:** Hyperlinks on drawing names

---

## Q5: Missing Data / 100% Coverage — How to Handle?

Currently the pipeline gives up after 3 attempts if completeness < 95%. For 7276 Concrete, it stopped at 76.5% with 4 missing drawings (A-13, A-24, A-25, A-5).

**How should we fix this?**

- **A) Increase max attempts** — allow more retries (e.g., 5 instead of 3) to extract from missing drawings
- **B) Lower the page-size threshold** — process drawings in smaller batches so the LLM doesn't miss any
- **C) Force-extract missing drawings** — after main pipeline completes, run a dedicated extraction pass ONLY for missing drawings, one at a time
- **D) All of the above** — max retries + targeted extraction for missing drawings
- **E) Something else** — describe

**Your answer:**  All of the above

---

## Q6: Missing CSI Codes — Are These Actually a Problem?

The completeness report flags 12 "missing" CSI codes (01-General Requirements, 02-Existing Conditions, 04-Masonry, etc.). But these are CSI codes from the **source data** that weren't matched to any extracted scope item.

For a **Concrete** trade report, is it actually expected to have CSI codes for Masonry (04), Plumbing (22), Finishes (09)?

- **A) Only count Concrete-related CSI codes** — filter CSI coverage to only codes relevant to the trade (03-xx for Concrete)
- **B) Ignore CSI coverage entirely** — drawing coverage is what matters for completeness
- **C) Keep as-is but weight it less** — reduce CSI weight in the completeness formula
- **D) Something else** — describe

**Your answer:** Only count Concrete-related CSI codes, Keep as-is but weight it less

---

## Q7: PDF Export — Same Changes as Word?

Currently PDF is a simplified version (max 100 items, flat list, no grouping). Should the PDF changes mirror the Word changes exactly?

- **A) Yes — same clean format as Word** (grouped by drawing, no metadata, project name header)
- **B) PDF should be even more minimal** — just a flat list of scope items, no drawing grouping
- **C) Don't generate PDF at all** — Word + CSV + JSON is enough

**Your answer:** Yes — same clean format as Word

---

## Q8: CSV Export — What Columns to Keep?

Currently CSV has 10 columns: Trade, CSI Code, CSI Division, Scope Item, Drawing, Drawing Title, Page, Source Snippet, Confidence, Classification Reason.

**Which columns should the export CSV have?**

- **A) Minimal** — Drawing, Scope Item, CSI Code only
- **B) Moderate** — Drawing, Drawing Title, Scope Item, CSI Code, CSI Division, Trade
- **C) Keep all current columns** — CSV is a data format, more columns = more useful
- **D) Custom** — list which columns you want

**Your answer:** Moderate

---

## Q9: JSON Export — What to Include?

Currently JSON includes everything (items, ambiguities, gotchas, completeness, quality, pipeline_stats).

- **A) Strip it to match Word** — only items + project info (no ambiguities/gotchas/completeness)
- **B) Keep JSON as the full data dump** — it's for developers/integrations, not end users
- **C) Something else** — describe

**Your answer:** Keep JSON as the full data dump

---

## Q10: SQL Database Connection — Which Database?

SQL connection is verified and working on the sandbox. We confirmed:
- `IFBIMIntegration_1.Projects.ProjectName` works
- 7276 = "SINGH RESIDENCE", 7298 = "Manchester Apartments", 7212 = "5 West 13th Street"

Note: `iFMasterDatabase_1` login fails — the credentials only work on `IFBIMIntegration_1`.

**Additional data from SQL — do you want any of these in the export?**

The Projects table also has: Location, City, StateID, ZipCode, StartDate, EndDate, Status, proj_address

- **A) Just project name** — that's all we need
- **B) Project name + location/address** — add to the document header
- **C) Project name + location + dates** — add project timeline info
- **D) Something else** — describe

**Your answer:** Just project name

---

## Q11: Should the Document Filename Change?

Currently: `7276_Concrete_20260407_113353.docx`

With the project name available, should it be:

- **A) Keep current format** — `7276_Concrete_20260407_113353.docx`
- **B) Add project name** — `SINGH_RESIDENCE_7276_Concrete_20260409.docx`
- **C) Professional format** — `Singh_Residence_Concrete_Scope_of_Work.docx`
- **D) Something else** — describe

**Your answer:** Professional format** — `7276_Concrete_Singh_Residence_Concrete_Scope_of_Work.docx

---

## Summary of Confirmed Removals (from your original request)

These will be removed from **all exported file formats** (Word, PDF, CSV, JSON where applicable):

| Remove | Currently In |
|--------|-------------|
| Completeness percentage in header | Word, PDF |
| CSI/Confidence/Source metadata per item | Word |
| Ambiguities section | Word, JSON |
| Gotchas section | Word, JSON |
| Completeness Report section | Word |
| "Generated by iFieldSmart ScopeAI Pipeline v1.0" footer | Word, PDF |

**UI remains unchanged** — all these details continue to display on the Streamlit interface.

---

## How to Respond

Edit this file directly — type your answers after "**Your answer:**" for each question. Or just tell me your answers in chat and I'll proceed with the design.
