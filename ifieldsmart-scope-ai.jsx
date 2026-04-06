import { useState, useEffect, useRef, useMemo, useCallback } from "react";

/*
 * iFieldSmart ScopeAI v4 — Fixed extraction + export + drawing viewer
 * - Stores file ArrayBuffer copies to prevent detachment
 * - Robust Claude API with error fallback
 * - Working CSV export with proper download trigger
 * - PDF.js with error handling
 */

const PDFJS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174";
let _pdfjs = null;

function loadPdfJs() {
  return new Promise((resolve, reject) => {
    if (_pdfjs) return resolve(_pdfjs);
    if (window.pdfjsLib) { _pdfjs = window.pdfjsLib; return resolve(_pdfjs); }
    const s = document.createElement("script");
    s.src = `${PDFJS_CDN}/pdf.min.js`;
    s.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}/pdf.worker.min.js`;
      _pdfjs = window.pdfjsLib;
      resolve(_pdfjs);
    };
    s.onerror = () => reject(new Error("Failed to load PDF.js"));
    document.head.appendChild(s);
  });
}

// ── Brand ────────────────────────────────────────────────────
const C = {
  gold:"#C4841D",goldL:"#E8A842",goldD:"#9A6510",
  blue:"#3B82F6",blueD:"#2563EB",
  bg:"#F3F4F6",white:"#FFFFFF",
  brd:"#E5E7EB",brdD:"#D1D5DB",
  t:"#111827",tm:"#6B7280",td:"#9CA3AF",
  ok:"#22C55E",okBg:"#D1FAE5",okT:"#065F46",
  w:"#F59E0B",wBg:"#FEF3C7",wT:"#92400E",
  er:"#EF4444",erBg:"#FEE2E2",erT:"#DC2626",
  headerBg:"#1E293B",headerBrd:"#334155",
};
const TC = ["#4FC3F7","#81C784","#FFB74D","#E57373","#BA68C8","#4DD0E1","#AED581","#FFD54F","#F06292","#9575CD","#4DB6AC","#DCE775","#FF8A65","#7986CB","#A1887F","#90A4AE","#FFF176","#CE93D8","#80CBC4","#FFAB91"];
const uid = () => Math.random().toString(36).substr(2, 9);

const DEFAULT_TRADES = [
  {name:"Abatement",csi:["02.*"],color:TC[0]},
  {name:"Acoustical Ceilings",csi:["09.5*"],color:TC[1]},
  {name:"Casework",csi:["06.4*","12.3*"],color:TC[2]},
  {name:"Ceramic Tile",csi:["09.3*"],color:TC[3]},
  {name:"Concrete",csi:["03.*"],color:TC[4]},
  {name:"Doors Frames & Hardware",csi:["08.1*","08.7*"],color:TC[5]},
  {name:"Earthwork",csi:["31.*"],color:TC[6]},
  {name:"Electrical",csi:["26.*","27.*","28.*"],color:TC[7]},
  {name:"Elevators",csi:["14.*"],color:TC[8]},
  {name:"Fire Sprinkler",csi:["21.*"],color:TC[10]},
  {name:"Flooring",csi:["09.6*"],color:TC[11]},
  {name:"Framing, Drywall & Insulation",csi:["09.2*","07.2*"],color:TC[12]},
  {name:"Glass & Glazing",csi:["08.4*","08.5*"],color:TC[13]},
  {name:"HVAC",csi:["23.*"],color:TC[14]},
  {name:"Painting & Coatings",csi:["09.9*"],color:TC[15]},
  {name:"Plumbing",csi:["22.*"],color:TC[16]},
  {name:"Roofing & Waterproofing",csi:["07.5*","07.6*"],color:TC[17]},
  {name:"Structural Steel",csi:["05.*"],color:TC[18]},
];

// ── Icons ────────────────────────────────────────────────────
const I = {
  file:<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>,
  check:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>,
  x:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>,
  plus:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>,
  right:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>,
  left:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>,
  down:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"/></svg>,
  play:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>,
  trash:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>,
  exp:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>,
  eye:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  draw:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>,
  bot:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/></svg>,
  ref:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>,
  search:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>,
  link:<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>,
  zIn:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>,
  zOut:<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>,
};

// ── Style helpers ────────────────────────────────────────────
const mkBtn = (v, sz) => ({
  display:"inline-flex",alignItems:"center",gap:5,fontFamily:"inherit",fontWeight:600,borderRadius:5,border:"none",cursor:"pointer",
  padding:sz==="sm"?"4px 10px":sz==="lg"?"9px 18px":"6px 14px",
  fontSize:sz==="sm"?11:sz==="lg"?13:12,
  ...(v==="pri"?{background:C.blueD,color:"#fff"}:
     v==="ok"?{background:C.ok,color:"#fff"}:
     v==="gold"?{background:C.gold,color:"#fff"}:
     v==="danger"?{background:C.erBg,color:C.erT,border:`1px solid #FECACA`}:
     v==="ghost"?{background:"transparent",color:C.tm,border:`1px solid ${C.brd}`}:
     {background:"#F3F4F6",color:C.t,border:`1px solid ${C.brd}`}),
});

// ── CSV Download helper ──────────────────────────────────────
function downloadCSV(rows, filename) {
  const header = "Trade,CSI Code,Scope Item,Source,Page,Confidence,Critical\n";
  const body = rows.map(i =>
    `"${(i.trade||'').replace(/"/g,'""')}","${i.csi||''}","${(i.text||'').replace(/"/g,'""')}","${i.source||''}","${i.page||''}","${i.confidence||''}","${i.critical||false}"`
  ).join("\n");
  const csvContent = header + body;
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

// ── Claude API ───────────────────────────────────────────────
async function claudeExtract(textChunks, trades, fileName, onLog) {
  const tradeList = trades.map(t => `- ${t.name} (CSI: ${t.csi.join(", ")})`).join("\n");
  const systemPrompt = `You are a construction scope intelligence expert. Extract ALL scope inclusions, requirements, and deliverables from the given construction document text.

AVAILABLE TRADES:
${tradeList}

CRITICAL RULES:
1. Extract EVERY specific, actionable requirement
2. Assign each to the correct trade
3. Include CSI section code if identifiable (format: XX XX XX)
4. Include the exact page number
5. Extract verbatim language from source
6. Flag critical coordination items

Respond with ONLY a JSON array. No markdown fences, no explanation. Each object:
{"trade":"exact trade name","text":"the scope text","csi":"XX XX XX","page":1,"confidence":0.9,"critical":false,"source_snippet":"5-10 word anchor from original"}`;

  const content = textChunks.map(c => `--- PAGE ${c.num} ---\n${c.text}`).join("\n\n");

  try {
    onLog(`Calling Claude API for ${fileName}...`);
    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 4096,
        system: systemPrompt,
        messages: [{ role: "user", content: `Extract all scope from "${fileName}":\n\n${content}` }],
      }),
    });

    if (!resp.ok) {
      onLog(`API returned ${resp.status}: ${resp.statusText}`);
      return [];
    }

    const data = await resp.json();
    if (data.error) {
      onLog(`API error: ${data.error.message || JSON.stringify(data.error)}`);
      return [];
    }

    const rawText = (data.content || []).map(c => c.text || "").join("");
    onLog(`Got ${rawText.length} chars response`);

    // Clean and parse JSON
    let cleaned = rawText.trim();
    if (cleaned.startsWith("```")) cleaned = cleaned.replace(/^```(?:json)?\n?/, "").replace(/\n?```$/, "");
    cleaned = cleaned.trim();

    try {
      const parsed = JSON.parse(cleaned);
      if (Array.isArray(parsed)) {
        onLog(`Parsed ${parsed.length} scope items`);
        return parsed;
      }
      onLog("Response was not an array");
      return [];
    } catch (parseErr) {
      onLog(`JSON parse error: ${parseErr.message}`);
      // Try to extract array from response
      const match = cleaned.match(/\[[\s\S]*\]/);
      if (match) {
        try {
          const arr = JSON.parse(match[0]);
          onLog(`Recovered ${arr.length} items from partial JSON`);
          return arr;
        } catch(e2) { onLog("Could not recover JSON"); }
      }
      return [];
    }
  } catch (err) {
    onLog(`Network error: ${err.message}`);
    return [];
  }
}

async function claudeAmbiguities(items, trades, onLog) {
  try {
    onLog("Detecting ambiguities...");
    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 2048,
        system: `You find overlapping scope between construction trades. Respond ONLY with a JSON array:\n[{"scope":"description","trades":["trade1","trade2"],"severity":"high|medium|low","recommendation":"which trade should own this"}]`,
        messages: [{ role: "user", content: `Trades: ${trades.map(t=>t.name).join(", ")}\n\nItems:\n${items.slice(0,30).map(i=>`[${i.trade}] ${i.text}`).join("\n")}` }],
      }),
    });
    if (!resp.ok) return [];
    const d = await resp.json();
    const raw = (d.content||[]).map(c=>c.text||"").join("").trim();
    const clean = raw.replace(/^```(?:json)?\n?/,"").replace(/\n?```$/,"").trim();
    const parsed = JSON.parse(clean);
    onLog(`Found ${parsed.length} ambiguities`);
    return Array.isArray(parsed) ? parsed : [];
  } catch(e) {
    onLog(`Ambiguity detection error: ${e.message}`);
    return [];
  }
}

// ═════════════════════════════════════════════════════════════
// PDF Drawing Viewer — with Draw a Highlight, Properties Panel
// ═════════════════════════════════════════════════════════════
function DrawingViewer({ arrayBuf, pageNum, findings, allItems, trades, fileName }) {
  const canvasRef = useRef(null);
  const overlayRef = useRef(null);
  const wrapRef = useRef(null);
  const [pg, setPg] = useState(pageNum || 1);
  const [np, setNp] = useState(0);
  const [scale, setScale] = useState(1.2);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);
  const docRef = useRef(null);
  const textItemsRef = useRef([]);
  const viewportRef = useRef(null);

  // Highlight state
  const [drawMode, setDrawMode] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState(null);
  const [drawRect, setDrawRect] = useState(null);
  const [highlights, setHighlights] = useState([]);
  const [selHL, setSelHL] = useState(null); // selected highlight for properties panel
  const [ctxMenu, setCtxMenu] = useState(null); // {x,y,hl}

  // Properties panel state
  const [hlTrade, setHlTrade] = useState("");
  const [hlText, setHlText] = useState("");
  const [hlCritical, setHlCritical] = useState(false);
  const [hlComment, setHlComment] = useState("");
  const [tradeSearch, setTradeSearch] = useState("");

  // Load PDF doc
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const lib = await loadPdfJs();
        const data = new Uint8Array(arrayBuf.slice(0));
        const doc = await lib.getDocument({ data }).promise;
        if (!cancel) { docRef.current = doc; setNp(doc.numPages); setLoaded(true); }
      } catch (e) { if (!cancel) setError(e.message); }
    })();
    return () => { cancel = true; };
  }, [arrayBuf]);

  // Render page + existing highlights + AI findings
  const renderPage = useCallback(async () => {
    if (!docRef.current || !canvasRef.current || !loaded) return;
    try {
      const page = await docRef.current.getPage(pg);
      const viewport = page.getViewport({ scale });
      viewportRef.current = viewport;
      const canvas = canvasRef.current;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext("2d");
      await page.render({ canvasContext: ctx, viewport }).promise;

      const tc = await page.getTextContent();
      textItemsRef.current = tc.items;

      // Draw AI-detected finding highlights
      const pgFindings = (findings || allItems || []).filter(f => f.page === pg);
      pgFindings.forEach(finding => {
        const trade = trades.find(t => t.name === finding.trade);
        const color = trade?.color || "#C4841D";
        const snippet = (finding.source_snippet || finding.text || "").toLowerCase();
        const words = snippet.split(/\s+/).filter(w => w.length > 3).slice(0, 6);
        if (!words.length) return;
        tc.items.forEach(item => {
          if (!item.str || !item.str.trim()) return;
          const lower = item.str.toLowerCase();
          const matchCount = words.filter(w => lower.includes(w)).length;
          if (matchCount >= Math.min(2, words.length)) {
            try {
              const [,,,, tx, ty] = item.transform;
              const x = tx * scale; const y = viewport.height - ty * scale;
              const w = (item.width || item.str.length * 5) * scale; const h = 14;
              ctx.save();
              ctx.fillStyle = color + "44";
              ctx.fillRect(x, y - h, w, h + 2);
              ctx.strokeStyle = color; ctx.lineWidth = 1.5;
              ctx.strokeRect(x, y - h, w, h + 2);
              ctx.restore();
            } catch (e) {}
          }
        });
      });

      // Draw user-created highlights
      highlights.filter(h => h.page === pg).forEach(hl => {
        const trade = trades.find(t => t.name === hl.trade);
        const color = trade?.color || C.blue;
        ctx.save();
        ctx.fillStyle = color + "35";
        ctx.fillRect(hl.x, hl.y, hl.w, hl.h);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(hl.x, hl.y, hl.w, hl.h);
        ctx.setLineDash([]);
        if (hl.critical) {
          ctx.fillStyle = C.er;
          ctx.font = "bold 10px Inter, sans-serif";
          ctx.fillText("★ CRITICAL", hl.x + 4, hl.y - 4);
        }
        if (hl.trade) {
          ctx.fillStyle = color;
          ctx.font = "bold 9px Inter, sans-serif";
          ctx.fillText(hl.trade, hl.x + 4, hl.y + 12);
        }
        ctx.restore();
      });

    } catch (e) { console.error("Render error:", e); }
  }, [pg, scale, loaded, findings, allItems, trades, highlights]);

  useEffect(() => { renderPage(); }, [renderPage]);

  // Resize overlay to match canvas
  useEffect(() => {
    if (!overlayRef.current || !canvasRef.current) return;
    overlayRef.current.width = canvasRef.current.width;
    overlayRef.current.height = canvasRef.current.height;
  }, [loaded, pg, scale]);

  // Get text items inside a rectangle
  function getTextInRect(rx, ry, rw, rh) {
    const items = textItemsRef.current;
    const vp = viewportRef.current;
    if (!items.length || !vp) return "";
    const texts = [];
    items.forEach(item => {
      if (!item.str || !item.str.trim()) return;
      try {
        const [,,,, tx, ty] = item.transform;
        const ix = tx * scale;
        const iy = vp.height - ty * scale - 10;
        const iw = (item.width || item.str.length * 5) * scale;
        const ih = 14;
        // Check overlap
        if (ix < rx + rw && ix + iw > rx && iy < ry + rh && iy + ih > ry) {
          texts.push(item.str);
        }
      } catch (e) {}
    });
    return texts.join(" ").trim();
  }

  // Mouse handlers for drawing
  function getCanvasPos(e) {
    const rect = overlayRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function handleMouseDown(e) {
    if (!drawMode) return;
    if (e.button === 2) return; // right-click handled separately
    const pos = getCanvasPos(e);
    setDrawing(true);
    setDrawStart(pos);
    setDrawRect(null);
    setCtxMenu(null);
  }

  function handleMouseMove(e) {
    if (!drawing || !drawStart) return;
    const pos = getCanvasPos(e);
    const overlay = overlayRef.current;
    if (!overlay) return;
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    const x = Math.min(drawStart.x, pos.x);
    const y = Math.min(drawStart.y, pos.y);
    const w = Math.abs(pos.x - drawStart.x);
    const h = Math.abs(pos.y - drawStart.y);
    ctx.save();
    ctx.fillStyle = C.blue + "22";
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = C.blue;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
    ctx.restore();
    setDrawRect({ x, y, w, h });
  }

  function handleMouseUp(e) {
    if (!drawing || !drawRect) { setDrawing(false); return; }
    setDrawing(false);
    // Clear overlay
    const overlay = overlayRef.current;
    if (overlay) overlay.getContext("2d").clearRect(0, 0, overlay.width, overlay.height);

    if (drawRect.w < 10 || drawRect.h < 10) return; // too small

    // Capture text under the rectangle
    const capturedText = getTextInRect(drawRect.x, drawRect.y, drawRect.w, drawRect.h);

    // Create new highlight
    const newHL = {
      id: uid(),
      page: pg,
      x: drawRect.x, y: drawRect.y, w: drawRect.w, h: drawRect.h,
      text: capturedText,
      trade: "",
      critical: false,
      comment: "",
    };
    setHighlights(prev => [...prev, newHL]);

    // Open properties panel for this highlight
    setSelHL(newHL);
    setHlTrade("");
    setHlText(capturedText);
    setHlCritical(false);
    setHlComment("");
    setTradeSearch("");

    // Exit draw mode
    setDrawMode(false);
    setDrawRect(null);
    setDrawStart(null);
  }

  // Right-click context menu on existing highlights
  function handleContextMenu(e) {
    e.preventDefault();
    const pos = getCanvasPos(e);
    const hit = highlights.filter(h => h.page === pg).find(h =>
      pos.x >= h.x && pos.x <= h.x + h.w && pos.y >= h.y && pos.y <= h.y + h.h
    );
    if (hit) {
      setCtxMenu({ x: e.clientX, y: e.clientY, hl: hit });
    } else {
      setCtxMenu(null);
    }
  }

  // Click to select existing highlight
  function handleCanvasClick(e) {
    if (drawMode) return;
    const pos = getCanvasPos(e);
    const hit = highlights.filter(h => h.page === pg).find(h =>
      pos.x >= h.x && pos.x <= h.x + h.w && pos.y >= h.y && pos.y <= h.y + h.h
    );
    if (hit) {
      setSelHL(hit);
      setHlTrade(hit.trade || "");
      setHlText(hit.text || "");
      setHlCritical(hit.critical || false);
      setHlComment(hit.comment || "");
      setTradeSearch("");
    } else {
      setCtxMenu(null);
    }
  }

  // Save highlight properties
  function saveHL() {
    if (!selHL) return;
    setHighlights(prev => prev.map(h =>
      h.id === selHL.id ? { ...h, trade: hlTrade, text: hlText, critical: hlCritical, comment: hlComment } : h
    ));
    setSelHL(null);
  }

  // Delete highlight
  function deleteHL(id) {
    setHighlights(prev => prev.filter(h => h.id !== id));
    if (selHL?.id === id) setSelHL(null);
    setCtxMenu(null);
  }

  const pgFindings = (findings || allItems || []).filter(f => f.page === pg);
  const pgHighlights = highlights.filter(h => h.page === pg);
  const filteredTrades = tradeSearch ? trades.filter(t => t.name.toLowerCase().includes(tradeSearch.toLowerCase())) : trades;

  if (error) return <div style={{padding:40,textAlign:"center",color:C.er}}>Failed to load PDF: {error}</div>;

  return (
    <div style={{display:"flex",flexDirection:"column",height:"100%",background:"#fff"}}>
      {/* Header */}
      <div style={{padding:"8px 16px",borderBottom:`1px solid ${C.brd}`}}>
        <div style={{fontSize:13,fontWeight:600}}>{fileName || "Drawing"}</div>
        <div style={{fontSize:11,color:C.blue}}>
          Page {pg} of {np}
          {pgFindings.length > 0 && ` • ${pgFindings.length} AI findings`}
          {pgHighlights.length > 0 && ` • ${pgHighlights.length} highlights`}
        </div>
      </div>

      {/* Toolbar */}
      <div style={{display:"flex",alignItems:"center",gap:6,padding:"6px 12px",borderBottom:`1px solid ${C.brd}`,background:"#FAFAFA"}}>
        <select style={{padding:"3px 8px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:11}}>
          <option>Trade/Scope</option>
          {trades.map(t => <option key={t.name}>{t.name}</option>)}
        </select>
        <div style={{flex:1}}/>
        {drawMode && <span style={{fontSize:11,color:C.blue,fontWeight:600,animation:"pulse 1s infinite"}}>🖊 Drawing mode — drag on drawing to highlight</span>}
        <button
          onClick={() => { setDrawMode(!drawMode); setCtxMenu(null); }}
          style={{
            ...mkBtn(drawMode ? "gold" : "pri", "sm"),
            ...(drawMode ? { boxShadow: `0 0 0 2px ${C.gold}44` } : {}),
          }}
        >
          {I.draw} {drawMode ? "Cancel" : "Draw a Highlight"}
        </button>
      </div>

      <div style={{display:"flex",flex:1,overflow:"hidden"}}>
        {/* Canvas area */}
        <div ref={wrapRef} style={{flex:1,overflow:"auto",background:"#E5E7EB",display:"flex",justifyContent:"center",padding:16,position:"relative"}}>
          {!loaded ? (
            <div style={{alignSelf:"center",color:C.tm}}>Loading PDF...</div>
          ) : (
            <div style={{position:"relative",display:"inline-block"}}>
              <canvas ref={canvasRef} style={{display:"block",boxShadow:"0 2px 20px rgba(0,0,0,0.12)",background:"#fff"}}/>
              {/* Overlay canvas for drawing rectangles */}
              <canvas
                ref={overlayRef}
                style={{
                  position:"absolute",top:0,left:0,width:"100%",height:"100%",
                  cursor:drawMode?"crosshair":"default",
                }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onClick={handleCanvasClick}
                onContextMenu={handleContextMenu}
              />
            </div>
          )}

          {/* Context menu */}
          {ctxMenu && (
            <div style={{
              position:"fixed",left:ctxMenu.x,top:ctxMenu.y,
              background:"#fff",border:`1px solid ${C.brd}`,borderRadius:6,
              boxShadow:"0 4px 16px rgba(0,0,0,0.15)",zIndex:100,padding:4,minWidth:150,
            }}>
              <div onClick={() => { setSelHL(ctxMenu.hl); setHlTrade(ctxMenu.hl.trade||""); setHlText(ctxMenu.hl.text||""); setHlCritical(ctxMenu.hl.critical||false); setHlComment(ctxMenu.hl.comment||""); setCtxMenu(null); }}
                style={{padding:"6px 12px",fontSize:12,cursor:"pointer",borderRadius:4,display:"flex",alignItems:"center",gap:6}}
                onMouseEnter={e=>e.currentTarget.style.background="#F3F4F6"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                ⚙ Properties
              </div>
              <div onClick={() => { setCtxMenu(null); }}
                style={{padding:"6px 12px",fontSize:12,cursor:"pointer",borderRadius:4,display:"flex",alignItems:"center",gap:6}}
                onMouseEnter={e=>e.currentTarget.style.background="#F3F4F6"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                🔗 CSI Codes
              </div>
              <div onClick={() => deleteHL(ctxMenu.hl.id)}
                style={{padding:"6px 12px",fontSize:12,cursor:"pointer",borderRadius:4,color:C.er,display:"flex",alignItems:"center",gap:6}}
                onMouseEnter={e=>e.currentTarget.style.background="#FEE2E2"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                🗑 Delete
              </div>
            </div>
          )}
        </div>

        {/* ── Highlight Properties Panel ─────────────────────── */}
        {selHL && (
          <div style={{width:280,borderLeft:`1px solid ${C.brd}`,background:"#fff",overflow:"auto",flexShrink:0}}>
            <div style={{padding:"12px 14px",borderBottom:`1px solid ${C.brd}`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <span style={{fontSize:13,fontWeight:700,display:"flex",alignItems:"center",gap:5}}>⚙ Highlight</span>
              <button onClick={() => setSelHL(null)} style={{background:"none",border:"none",cursor:"pointer",color:C.td}}>{I.x}</button>
            </div>

            <div style={{padding:"12px 14px"}}>
              {/* Trade selector with search */}
              <label style={{fontSize:11,fontWeight:600,color:C.tm,display:"block",marginBottom:4}}>Trades</label>
              <select
                value={hlTrade}
                onChange={e => setHlTrade(e.target.value)}
                style={{width:"100%",padding:"6px 8px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:12,marginBottom:4,background:"#fff"}}
              >
                <option value="">No trades selected</option>
                {trades.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
              </select>

              {/* Search filter for trades */}
              <div style={{position:"relative",marginBottom:12}}>
                <input
                  value={tradeSearch}
                  onChange={e => setTradeSearch(e.target.value)}
                  placeholder="Search trades..."
                  style={{width:"100%",padding:"5px 8px 5px 24px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:11,boxSizing:"border-box"}}
                />
                <span style={{position:"absolute",left:6,top:6,color:C.td}}>{I.search}</span>
                {tradeSearch && (
                  <div style={{position:"absolute",top:"100%",left:0,right:0,background:"#fff",border:`1px solid ${C.brd}`,borderRadius:4,zIndex:10,maxHeight:120,overflow:"auto",boxShadow:"0 2px 8px rgba(0,0,0,0.1)"}}>
                    {filteredTrades.map(t => (
                      <div key={t.name} onClick={() => { setHlTrade(t.name); setTradeSearch(""); }}
                        style={{padding:"5px 8px",fontSize:11,cursor:"pointer",display:"flex",alignItems:"center",gap:6}}
                        onMouseEnter={e=>e.currentTarget.style.background="#F3F4F6"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                        <div style={{width:10,height:10,borderRadius:2,background:t.color}}/> {t.name}
                      </div>
                    ))}
                    {filteredTrades.length === 0 && <div style={{padding:"8px",fontSize:11,color:C.td}}>No trades match</div>}
                  </div>
                )}
              </div>

              {/* Text under highlight */}
              <label style={{fontSize:11,fontWeight:600,color:C.tm,display:"block",marginBottom:4}}>Text</label>
              <textarea
                value={hlText}
                onChange={e => setHlText(e.target.value)}
                style={{width:"100%",padding:"6px 8px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:11,minHeight:70,fontFamily:"inherit",resize:"vertical",boxSizing:"border-box",marginBottom:2}}
              />
              <div style={{fontSize:10,color:C.td,marginBottom:12}}>Text under the highlight</div>

              {/* Critical checkbox */}
              <label style={{fontSize:12,display:"flex",alignItems:"center",gap:6,marginBottom:4,cursor:"pointer"}}>
                <input type="checkbox" checked={hlCritical} onChange={e => setHlCritical(e.target.checked)} style={{accentColor:C.er}}/>
                <span style={{fontWeight:500}}>Critical</span>
              </label>
              <div style={{fontSize:10,color:C.td,marginBottom:14}}>Critical highlights receive more attention in reports</div>

              {/* Action buttons */}
              <div style={{display:"flex",gap:8}}>
                <button onClick={() => deleteHL(selHL.id)} style={mkBtn("danger","sm")}>{I.trash} Delete</button>
                <button onClick={saveHL} style={{...mkBtn("pri","sm"),flex:1}}>Save</button>
              </div>

              {/* Comments section */}
              <div style={{marginTop:16,borderTop:`1px solid ${C.brd}`,paddingTop:12}}>
                <label style={{fontSize:11,fontWeight:600,color:C.tm,display:"block",marginBottom:4}}>Comments</label>
                <label style={{fontSize:11,fontWeight:600,color:C.tm,display:"block",marginBottom:4}}>Comment</label>
                <div style={{position:"relative"}}>
                  <textarea
                    value={hlComment}
                    onChange={e => setHlComment(e.target.value)}
                    placeholder="Type your comment..."
                    style={{width:"100%",padding:"6px 28px 6px 8px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:11,minHeight:50,fontFamily:"inherit",resize:"vertical",boxSizing:"border-box"}}
                  />
                  <button onClick={saveHL} style={{position:"absolute",right:6,bottom:8,background:"none",border:"none",cursor:"pointer",color:C.blue,fontSize:14}} title="Send">▸</button>
                </div>
                <div style={{fontSize:10,color:C.td,marginTop:4}}>Users of your organization can see these comments. Comments will appear in the PDF export report along with highlights.</div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Bottom bar */}
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"8px 16px",borderTop:`1px solid ${C.brd}`,background:"#FAFAFA"}}>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <button onClick={() => setPg(p => Math.max(1, p - 1))} disabled={pg <= 1} style={mkBtn("ghost","sm")}>{I.left}</button>
          <span style={{fontSize:12,fontWeight:600}}>Page {pg}/{np}</span>
          <button onClick={() => setPg(p => Math.min(np, p + 1))} disabled={pg >= np} style={mkBtn("ghost","sm")}>{I.right}</button>
          <div style={{width:1,height:16,background:C.brd}}/>
          <button onClick={() => setScale(s => Math.min(3, s + 0.2))} style={mkBtn("ghost","sm")}>{I.zIn}</button>
          <span style={{fontSize:11,color:C.tm}}>{Math.round(scale * 100)}%</span>
          <button onClick={() => setScale(s => Math.max(0.4, s - 0.2))} style={mkBtn("ghost","sm")}>{I.zOut}</button>
        </div>
        <div style={{display:"flex",gap:8}}>
          <button style={mkBtn("ghost","sm")}>{I.trash} Ignore</button>
          <button style={{...mkBtn("pri","sm"),background:C.er}}>{I.exp} Export</button>
        </div>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// Scope of Work Report per trade
// ═════════════════════════════════════════════════════════════
function ScopeReport({ trade, items, trades, fileBuffers, onViewDrawing }) {
  const tradeItems = items.filter(i => i.trade === trade.name && i.on);

  const bySource = {};
  tradeItems.forEach(it => {
    const k = `${it.source}|${it.page}`;
    if (!bySource[k]) bySource[k] = { source: it.source, page: it.page, items: [] };
    bySource[k].items.push(it);
  });

  return (
    <div style={{display:"flex",flexDirection:"column",height:"100%"}}>
      <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.brd}`,background:"#fff",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div>
          <h2 style={{fontSize:17,fontWeight:700,margin:0}}>{trade.name} Scope of Work</h2>
          <p style={{margin:"2px 0 0",fontSize:12,color:C.tm}}>Review and update report to your taste • {tradeItems.length} items</p>
        </div>
        <button onClick={() => downloadCSV(tradeItems, `${trade.name.replace(/\W/g,"_")}_Scope.csv`)}
          style={{...mkBtn("pri","md")}}>{I.exp} Export</button>
      </div>

      <div style={{flex:1,overflow:"auto",padding:20}}>
        <div style={{border:`1px solid ${C.brd}`,borderRadius:8,background:"#fff"}}>
          <div style={{padding:"10px 16px",borderBottom:`1px solid ${C.brd}`,fontWeight:700,fontSize:13,fontFamily:"monospace"}}>Job Specific Items</div>
          {tradeItems.map(it => (
            <div key={it.id} style={{display:"flex",gap:10,padding:"10px 16px",borderBottom:`1px solid ${C.brd}`,background:it.critical?C.erBg:"#fff"}}>
              <input type="checkbox" checked={it.on} readOnly style={{marginTop:3,accentColor:C.blue}}/>
              <div style={{flex:1}}>
                <div style={{fontSize:13,lineHeight:1.6,color:C.t}}>
                  {it.text}
                  {it.source_snippet && fileBuffers[it.source] && (
                    <button onClick={() => onViewDrawing(it)}
                      style={{background:"none",border:"none",cursor:"pointer",color:C.blue,marginLeft:6,padding:0,verticalAlign:"middle"}}
                      title="View source on drawing">{I.link}</button>
                  )}
                </div>
                {it.csi && <div style={{fontSize:10,color:C.tm,marginTop:2}}>CSI {it.csi} • {it.source} p.{it.page} • {Math.round((it.confidence||0.85)*100)}%</div>}
              </div>
            </div>
          ))}
          {tradeItems.length === 0 && <div style={{padding:30,textAlign:"center",color:C.td}}>No scope items for this trade.</div>}
        </div>

        {/* Source Drawing References */}
        {Object.keys(bySource).length > 0 && (
          <div style={{marginTop:20}}>
            <h3 style={{fontSize:13,fontWeight:700,marginBottom:8}}>Source Drawing References</h3>
            <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(260px,1fr))",gap:8}}>
              {Object.values(bySource).map((sp, i) => (
                <div key={i} onClick={() => {
                  if (fileBuffers[sp.source]) onViewDrawing({ source: sp.source, page: sp.page, source_snippet: sp.items[0]?.source_snippet || "" });
                }}
                  style={{border:`1px solid ${C.brd}`,borderRadius:8,padding:12,cursor:"pointer",background:"#FAFAFA"}}>
                  <div style={{display:"flex",alignItems:"center",gap:8}}>
                    <div style={{width:28,height:28,borderRadius:6,background:trade.color+"22",display:"flex",alignItems:"center",justifyContent:"center",color:trade.color}}>{I.file}</div>
                    <div>
                      <div style={{fontSize:12,fontWeight:600}}>{sp.source}</div>
                      <div style={{fontSize:11,color:C.tm}}>Page {sp.page} • {sp.items.length} item{sp.items.length>1?"s":""}</div>
                    </div>
                  </div>
                  <div style={{marginTop:6,fontSize:11,color:C.blue,fontWeight:500}}>Click to view highlighted drawing →</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// MAIN APP
// ═════════════════════════════════════════════════════════════
export default function ScopeAI() {
  const [step, setStep] = useState("upload");
  const [files, setFiles] = useState([]);
  const [trades, setTrades] = useState(DEFAULT_TRADES);
  const [items, setItems] = useState([]);
  const [ambs, setAmbs] = useState([]);

  // Store ArrayBuffer copies keyed by filename
  const [fileBuffers, setFileBuffers] = useState({});

  const [logs, setLogs] = useState([]);
  const [procStage, setProcStage] = useState(0);

  const [sideTab, setSideTab] = useState("findings");
  const [mainView, setMainView] = useState("export");
  const [selTrade, setSelTrade] = useState(null);
  const [drawState, setDrawState] = useState(null);
  const [showEdit, setShowEdit] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [nn, setNn] = useState("");
  const [nc, setNc] = useState("");
  const [nco, setNco] = useState(TC[0]);

  const fileRef = useRef(null);
  const [drag, setDrag] = useState(false);

  const tradeCounts = useMemo(() => {
    const m = {};
    items.forEach(i => { m[i.trade] = (m[i.trade] || 0) + 1; });
    return m;
  }, [items]);

  const findingsByPage = useMemo(() => {
    const m = {};
    items.forEach(it => {
      const k = `${it.source}||${it.page}`;
      if (!m[k]) m[k] = { source: it.source, page: it.page, items: [], label: `Page ${it.page} - ${it.source.substring(0, 28)}` };
      m[k].items.push(it);
    });
    return Object.values(m).sort((a, b) => a.source.localeCompare(b.source) || a.page - b.page);
  }, [items]);

  // ── Add files ──────────────────────────────────────────────
  const addFiles = useCallback((fl) => {
    const pdfs = Array.from(fl).filter(f => f.name.endsWith(".pdf") || f.type === "application/pdf");
    setFiles(p => [...p, ...pdfs.map(f => ({
      id: uid(), name: f.name, size: f.size, file: f,
      type: f.name.toLowerCase().includes("spec") ? "spec" : "drawing"
    }))]);
  }, []);

  // ── Run extraction ─────────────────────────────────────────
  const runExtraction = useCallback(async () => {
    setStep("processing");
    setLogs([]);
    setProcStage(0);
    const log = (m) => setLogs(p => [...p, m]);

    // 1. Read all files into ArrayBuffer copies
    log("Reading uploaded files...");
    const buffers = {};
    for (const f of files) {
      try {
        const ab = await f.file.arrayBuffer();
        buffers[f.name] = ab.slice(0); // Independent copy
        log(`Read ${f.name} (${(ab.byteLength / 1024 / 1024).toFixed(1)} MB)`);
      } catch (e) {
        log(`Error reading ${f.name}: ${e.message}`);
      }
    }
    setFileBuffers(buffers);

    // 2. Load PDF.js and extract text
    setProcStage(1);
    log("Loading PDF.js library...");
    let pdfjsLib;
    try {
      pdfjsLib = await loadPdfJs();
      log("PDF.js loaded successfully");
    } catch (e) {
      log(`PDF.js load failed: ${e.message}. Extraction cannot proceed.`);
      await new Promise(r => setTimeout(r, 2000));
      setStep("main");
      return;
    }

    const allPages = [];
    for (const [name, buf] of Object.entries(buffers)) {
      try {
        log(`Extracting text from ${name}...`);
        const data = new Uint8Array(buf.slice(0));
        const doc = await pdfjsLib.getDocument({ data }).promise;
        for (let i = 1; i <= doc.numPages; i++) {
          const page = await doc.getPage(i);
          const tc = await page.getTextContent();
          const text = tc.items.map(x => x.str).join(" ");
          if (text.trim().length > 20) {
            allPages.push({ num: i, text, fileName: name });
          }
        }
        log(`${name}: ${doc.numPages} pages processed`);
      } catch (e) {
        log(`Error processing ${name}: ${e.message}`);
      }
    }
    log(`Total: ${allPages.length} pages with text content`);

    if (allPages.length === 0) {
      log("No text content found in any files. These may be scanned drawings.");
      await new Promise(r => setTimeout(r, 2000));
      setStep("main");
      return;
    }

    // 3. Call Claude API for scope extraction
    setProcStage(2);
    const allItems = [];
    const CHUNK = 10;
    for (let i = 0; i < allPages.length; i += CHUNK) {
      const chunk = allPages.slice(i, i + CHUNK);
      const fn = chunk[0].fileName;
      log(`Extracting scope from pages ${i + 1}-${Math.min(i + CHUNK, allPages.length)} of ${fn}...`);

      const extracted = await claudeExtract(chunk, trades, fn, log);
      extracted.forEach(x => {
        const trade = trades.find(t => t.name === x.trade);
        allItems.push({
          id: uid(),
          trade: x.trade || "Unassigned",
          tradeColor: trade?.color || "#999",
          text: x.text || "",
          csi: x.csi || "",
          source: fn,
          page: x.page || 1,
          confidence: x.confidence || 0.85,
          critical: x.critical || false,
          source_snippet: x.source_snippet || "",
          on: true,
        });
      });
    }
    log(`Extracted ${allItems.length} total scope items`);

    // 4. Ambiguity detection
    setProcStage(3);
    let ambiguities = [];
    if (allItems.length > 0) {
      ambiguities = await claudeAmbiguities(allItems, trades, log);
      ambiguities = ambiguities.map(a => ({ ...a, id: uid(), resolved: false, assignedTo: null }));
    }

    setProcStage(4);
    log(`✓ Pipeline complete: ${allItems.length} items, ${ambiguities.length} ambiguities`);

    setItems(allItems);
    setAmbs(ambiguities);

    await new Promise(r => setTimeout(r, 800));
    setStep("main");
    setMainView("export");
  }, [files, trades]);

  // ── View drawing ───────────────────────────────────────────
  const viewDrawing = useCallback((finding) => {
    const buf = fileBuffers[finding.source];
    if (buf) {
      setDrawState({
        buf,
        page: finding.page,
        findings: items.filter(i => i.source === finding.source),
        fileName: finding.source,
      });
      setMainView("drawing");
    }
  }, [fileBuffers, items]);

  // ═════════════════════════════════════════════════════════════
  return (
    <div style={{fontFamily:"'Inter','Segoe UI',sans-serif",height:"100vh",display:"flex",flexDirection:"column",overflow:"hidden",fontSize:13,color:C.t,background:C.bg}}>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>

      {/* ── Top Bar ─────────────────────────────────────────── */}
      <div style={{display:"flex",alignItems:"center",padding:"0 16px",height:46,background:C.headerBg,borderBottom:`1px solid ${C.headerBrd}`,flexShrink:0,gap:10}}>
        <div style={{width:26,height:26,borderRadius:6,background:`linear-gradient(135deg,${C.gold},${C.goldD})`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:10,fontWeight:800,color:"#fff"}}>iF</div>
        <span style={{fontWeight:700,fontSize:14,color:"#fff"}}>ScopeAI</span>
        <div style={{flex:1}}/>
        {step==="main" && <span style={{fontSize:11,color:C.ok,fontWeight:600}}>● {items.length} items extracted</span>}
      </div>

      {/* ═══ UPLOAD ════════════════════════════════════════════ */}
      {step === "upload" && (
        <div style={{flex:1,overflow:"auto",display:"flex",justifyContent:"center",padding:40}}>
          <div style={{maxWidth:660,width:"100%"}}>
            <h2 style={{fontSize:22,fontWeight:700,margin:"0 0 4px"}}>Step 1: Upload Documents</h2>
            <p style={{color:C.tm,margin:"0 0 20px",fontSize:13}}>Upload contract drawings and specifications. AI extracts real scope from your actual documents.</p>
            <div onDragOver={e=>{e.preventDefault();setDrag(true);}} onDragLeave={()=>setDrag(false)}
              onDrop={e=>{e.preventDefault();setDrag(false);addFiles(e.dataTransfer.files);}}
              onClick={()=>fileRef.current?.click()}
              style={{border:`2px dashed ${drag?C.blue:C.brd}`,borderRadius:10,padding:44,textAlign:"center",cursor:"pointer",background:drag?"#EFF6FF":"#fff"}}>
              <input ref={fileRef} type="file" accept=".pdf" multiple hidden onChange={e=>{if(e.target.files?.length)addFiles(e.target.files);}}/>
              <div style={{fontSize:15,fontWeight:600}}>Drop PDFs here or click to browse</div>
              <div style={{fontSize:12,color:C.td,marginTop:4}}>Contract Drawings, Specifications, Addenda</div>
            </div>
            {files.map(f => (
              <div key={f.id} style={{display:"flex",alignItems:"center",gap:10,padding:"8px 12px",background:"#fff",borderRadius:6,marginTop:6,border:`1px solid ${C.brd}`}}>
                <div style={{color:C.blue}}>{I.file}</div>
                <div style={{flex:1}}><div style={{fontSize:12,fontWeight:500}}>{f.name}</div><div style={{fontSize:10,color:C.td}}>{(f.size/1048576).toFixed(1)} MB</div></div>
                <select value={f.type} onChange={e=>setFiles(p=>p.map(x=>x.id===f.id?{...x,type:e.target.value}:x))} style={{padding:"3px 6px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:11}}>
                  <option value="drawing">Drawing</option><option value="spec">Specification</option>
                </select>
                <button onClick={()=>setFiles(p=>p.filter(x=>x.id!==f.id))} style={{background:"none",border:"none",cursor:"pointer",color:C.td}}>{I.trash}</button>
              </div>
            ))}
            <div style={{display:"flex",justifyContent:"flex-end",marginTop:24}}>
              <button onClick={()=>setStep("trades")} disabled={!files.length}
                style={{...mkBtn(files.length?"pri":"ghost","lg"),opacity:files.length?1:0.4}}>
                Continue to Trade Setup {I.right}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══ TRADES ════════════════════════════════════════════ */}
      {step === "trades" && (
        <div style={{flex:1,overflow:"auto",padding:24}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:14}}>
            <div>
              <h2 style={{fontSize:20,fontWeight:700,margin:0}}>Trades <span style={{color:C.ok,fontWeight:400,fontSize:13}}>Ready</span></h2>
              <p style={{color:C.tm,margin:"2px 0 0",fontSize:12}}>Add Trades to the project and run search</p>
            </div>
            <div style={{display:"flex",gap:8}}>
              <button style={mkBtn("light","md")} onClick={()=>{setShowCreate(true);setShowEdit(null);}}>{I.plus} New Trade</button>
              <button onClick={runExtraction} style={{...mkBtn("pri","md")}}>{I.ref} Save and Run</button>
            </div>
          </div>
          <div style={{display:"grid",gridTemplateColumns:showCreate||showEdit?"1fr 280px":"1fr",gap:16}}>
            <div style={{border:`1px solid ${C.brd}`,borderRadius:8,background:"#fff",overflow:"auto",maxHeight:"calc(100vh - 200px)"}}>
              {trades.map(t=>(
                <div key={t.name} onClick={()=>{setShowEdit({...t});setShowCreate(false);}}
                  style={{display:"flex",alignItems:"center",gap:8,padding:"8px 14px",borderBottom:`1px solid ${C.brd}`,cursor:"pointer",background:showEdit?.name===t.name?"#EFF6FF":"#fff"}}>
                  <div style={{width:11,height:11,borderRadius:3,background:t.color}}/>
                  <span style={{flex:1,fontSize:12,fontWeight:500}}>{t.name}</span>
                  <div style={{display:"flex",gap:3,flexWrap:"wrap"}}>{t.csi.map(c=><span key={c} style={{padding:"1px 5px",borderRadius:3,fontSize:9,fontWeight:600,background:t.color+"18",color:t.color}}>{c}</span>)}</div>
                </div>
              ))}
            </div>
            {(showCreate||showEdit)&&(
              <div style={{border:`1px solid ${C.brd}`,borderRadius:8,background:"#fff",padding:14,alignSelf:"flex-start"}}>
                <div style={{display:"flex",justifyContent:"space-between",marginBottom:10}}>
                  <span style={{fontWeight:700,fontSize:12}}>{showCreate?"Create Trade":"Edit Trade"}</span>
                  <button onClick={()=>{setShowCreate(false);setShowEdit(null);}} style={{background:"none",border:"none",cursor:"pointer",color:C.td}}>{I.x}</button>
                </div>
                <label style={{fontSize:10,fontWeight:600,color:C.tm}}>Name</label>
                <input style={{width:"100%",padding:"5px 8px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:12,marginTop:3,marginBottom:8,boxSizing:"border-box"}}
                  value={showCreate?nn:(showEdit?.name||"")} onChange={e=>showCreate?setNn(e.target.value):setShowEdit({...showEdit,name:e.target.value})}/>
                <label style={{fontSize:10,fontWeight:600,color:C.tm}}>CSI Codes (comma sep)</label>
                <input style={{width:"100%",padding:"5px 8px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:12,marginTop:3,marginBottom:8,boxSizing:"border-box"}}
                  value={showCreate?nc:(showEdit?.csi?.join(", ")||"")} onChange={e=>{const v=e.target.value;showCreate?setNc(v):setShowEdit({...showEdit,csi:v.split(",").map(c=>c.trim()).filter(Boolean)});}}/>
                <label style={{fontSize:10,fontWeight:600,color:C.tm}}>Color</label>
                <div style={{display:"flex",flexWrap:"wrap",gap:4,margin:"4px 0 10px"}}>{TC.map(c=><div key={c} onClick={()=>showCreate?setNco(c):setShowEdit({...showEdit,color:c})} style={{width:16,height:16,borderRadius:3,background:c,cursor:"pointer",border:(showCreate?nco:showEdit?.color)===c?"2px solid #000":"2px solid transparent"}}/>)}</div>
                <button onClick={()=>{
                  if(showCreate&&nn.trim()){setTrades(p=>[...p,{name:nn.trim(),csi:nc.split(",").map(c=>c.trim()).filter(Boolean),color:nco}]);setNn("");setNc("");setShowCreate(false);}
                  else if(showEdit){setTrades(p=>p.map(t=>t.name===showEdit.name?showEdit:t));setShowEdit(null);}
                }} style={{...mkBtn("pri"),width:"100%"}}>{showCreate?"Create":"Save"}</button>
              </div>
            )}
          </div>
          <div style={{display:"flex",justifyContent:"flex-start",marginTop:16}}>
            <button onClick={()=>setStep("upload")} style={mkBtn("ghost","md")}>{I.left} Back</button>
          </div>
        </div>
      )}

      {/* ═══ PROCESSING ════════════════════════════════════════ */}
      {step === "processing" && (
        <div style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center"}}>
          <div style={{width:500,background:"#fff",border:`1px solid ${C.brd}`,borderRadius:10,padding:24}}>
            <div style={{textAlign:"center",marginBottom:16}}>
              <div style={{fontSize:18,fontWeight:700}}>AI Agents Processing</div>
              <div style={{color:C.tm,fontSize:12,marginTop:2}}>Extracting scope from your documents...</div>
            </div>
            {["Spec Parser","Scope Extractor","Trade Classifier","Ambiguity Detector","Complete"].map((a,i)=>{
              const colors=["#4FC3F7","#81C784","#FFB74D","#E57373","#22C55E"];
              const s=i<procStage?"done":i===procStage?"active":"wait";
              return (
                <div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0"}}>
                  <div style={{width:26,height:26,borderRadius:5,background:colors[i]+"22",display:"flex",alignItems:"center",justifyContent:"center",color:colors[i]}}>{I.bot}</div>
                  <div style={{flex:1}}>
                    <div style={{fontSize:11,fontWeight:600}}>{a}</div>
                    <div style={{fontSize:10,color:s==="done"?C.ok:C.tm}}>{s==="done"?"Complete":s==="active"?"Working...":"Waiting"}</div>
                  </div>
                  {s==="done"&&<span style={{color:C.ok}}>{I.check}</span>}
                </div>
              );
            })}
            <div style={{marginTop:10,maxHeight:120,overflow:"auto",background:"#F9FAFB",borderRadius:6,padding:8,border:`1px solid ${C.brd}`,fontSize:10,fontFamily:"monospace"}}>
              {logs.map((l,i)=><div key={i} style={{color:C.td,padding:"1px 0"}}>→ {l}</div>)}
              {logs.length===0 && <div style={{color:C.td}}>Starting...</div>}
            </div>
          </div>
        </div>
      )}

      {/* ═══ MAIN VIEW ═════════════════════════════════════════ */}
      {step === "main" && (
        <div style={{display:"flex",flex:1,overflow:"hidden"}}>
          {/* ── Sidebar ──────────────────────────────────────── */}
          <div style={{width:240,background:"#fff",borderRight:`1px solid ${C.brd}`,display:"flex",flexDirection:"column",flexShrink:0}}>
            <div style={{display:"flex",borderBottom:`1px solid ${C.brd}`}}>
              {["Drawings","Specs","Findings"].map(tab=>(
                <button key={tab} onClick={()=>setSideTab(tab.toLowerCase())}
                  style={{flex:1,padding:"9px 4px",fontSize:11,fontWeight:sideTab===tab.toLowerCase()?600:400,border:"none",cursor:"pointer",fontFamily:"inherit",
                    background:sideTab===tab.toLowerCase()?"#fff":"#F9FAFB",
                    color:sideTab===tab.toLowerCase()?C.blue:C.tm,
                    borderBottom:sideTab===tab.toLowerCase()?`2px solid ${C.blue}`:"2px solid transparent"}}>
                  {tab}
                </button>
              ))}
            </div>
            <div style={{padding:"8px 10px",borderBottom:`1px solid ${C.brd}`}}>
              <div style={{fontSize:9,fontWeight:600,color:C.td,textTransform:"uppercase",marginBottom:3}}>Revision</div>
              <select style={{width:"100%",padding:"4px 6px",borderRadius:4,border:`1px solid ${C.brd}`,fontSize:11}}>
                <option>Complete Set</option>
              </select>
            </div>

            <div style={{flex:1,overflow:"auto"}}>
              {sideTab==="findings" && findingsByPage.map(fp=>(
                <div key={fp.source+fp.page} onClick={()=>{
                  const buf=fileBuffers[fp.source];
                  if(buf){setDrawState({buf,page:fp.page,findings:fp.items,fileName:fp.source});setMainView("drawing");}
                }}
                  style={{display:"flex",alignItems:"center",gap:6,padding:"6px 10px",cursor:"pointer",borderBottom:`1px solid #F3F4F6`,fontSize:11}}>
                  <span style={{color:C.td}}>{I.file}</span>
                  <span style={{flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{fp.label}</span>
                  <span style={{background:C.gold,color:"#fff",fontSize:9,fontWeight:700,padding:"1px 5px",borderRadius:6,minWidth:14,textAlign:"center"}}>{fp.items.length}</span>
                </div>
              ))}
              {sideTab==="findings" && findingsByPage.length===0 && (
                <div style={{padding:20,textAlign:"center",color:C.td,fontSize:11}}>No findings yet. Run extraction first.</div>
              )}
              {(sideTab==="drawings"||sideTab==="specs")&&["GENERAL","STRUCTURAL","ARCHITECTURAL","FIRE PROTECTION","PLUMBING","MECHANICAL","ELECTRICAL"].map(cat=>(
                <div key={cat} style={{padding:"7px 10px",fontSize:11,fontWeight:500,cursor:"pointer",borderBottom:`1px solid #F3F4F6`,display:"flex",alignItems:"center",gap:5}}>
                  {I.right} {cat}
                </div>
              ))}
            </div>
          </div>

          {/* ── Main Content ─────────────────────────────────── */}
          <div style={{flex:1,overflow:"auto",background:C.bg}}>
            {/* EXPORT VIEW */}
            {mainView==="export" && (
              <div style={{padding:20}}>
                <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}>
                  <div>
                    <h2 style={{fontSize:17,fontWeight:700,margin:0}}>Export</h2>
                    <p style={{color:C.tm,margin:"2px 0 0",fontSize:12}}>Generate and export reports for trades</p>
                  </div>
                  <button onClick={()=>downloadCSV(items.filter(i=>i.on),"All_Trades_Scope.csv")}
                    style={mkBtn("ok","md")}>{I.ref} Export All</button>
                </div>

                <div style={{border:`1px solid ${C.brd}`,borderRadius:8,background:"#fff"}}>
                  <div style={{display:"grid",gridTemplateColumns:"auto 1fr 60px 70px",padding:"8px 14px",borderBottom:`1px solid ${C.brd}`,fontSize:10,fontWeight:600,color:C.td,textTransform:"uppercase"}}>
                    <span style={{width:12}}/><span>Trade</span><span style={{textAlign:"center"}}>Status</span><span style={{textAlign:"right"}}>Items</span>
                  </div>
                  {trades.map(t=>{
                    const cnt = tradeCounts[t.name]||0;
                    return (
                      <div key={t.name} onClick={()=>{if(cnt>0){setSelTrade(t);setMainView("report");}}}
                        style={{display:"grid",gridTemplateColumns:"auto 1fr 60px 70px",gap:6,alignItems:"center",padding:"9px 14px",borderBottom:`1px solid ${C.brd}`,cursor:cnt>0?"pointer":"default",opacity:cnt>0?1:0.5}}>
                        <div style={{width:10,height:10,borderRadius:3,background:t.color}}/>
                        <span style={{fontSize:12,fontWeight:500}}>{t.name}</span>
                        <div style={{textAlign:"center"}}><span style={{padding:"1px 6px",borderRadius:6,fontSize:10,fontWeight:600,background:cnt>0?C.okBg:"#F3F4F6",color:cnt>0?C.okT:C.td}}>{cnt>0?"Ready":"—"}</span></div>
                        <span style={{textAlign:"right",fontSize:11,color:C.tm,fontWeight:600}}>{cnt||""}</span>
                      </div>
                    );
                  })}
                </div>

                {items.length===0 && (
                  <div style={{marginTop:20,padding:24,background:"#fff",border:`1px solid ${C.brd}`,borderRadius:8,textAlign:"center"}}>
                    <div style={{fontSize:14,fontWeight:600,color:C.tm}}>No scope items yet</div>
                    <div style={{fontSize:12,color:C.td,marginTop:4}}>Upload documents and run extraction to see results here.</div>
                    <button onClick={()=>setStep("upload")} style={{...mkBtn("pri","md"),marginTop:12}}>Go to Upload</button>
                  </div>
                )}

                {/* Ambiguities */}
                {ambs.length>0 && (
                  <div style={{marginTop:20}}>
                    <h3 style={{fontSize:14,fontWeight:700,marginBottom:8}}>Ambiguities ({ambs.filter(a=>!a.resolved).length} unresolved)</h3>
                    {ambs.map(a=>(
                      <div key={a.id} style={{border:`1px solid ${C.brd}`,borderRadius:8,background:"#fff",padding:12,marginBottom:6,borderLeft:`4px solid ${a.severity==="high"?C.er:a.severity==="medium"?C.w:"#3B82F6"}`,opacity:a.resolved?0.5:1}}>
                        <div style={{display:"flex",alignItems:"center",gap:5,marginBottom:3}}>
                          <span style={{padding:"1px 5px",borderRadius:4,fontSize:9,fontWeight:700,
                            background:a.severity==="high"?C.erBg:a.severity==="medium"?C.wBg:"#DBEAFE",
                            color:a.severity==="high"?C.erT:a.severity==="medium"?C.wT:"#2563EB"}}>{(a.severity||"").toUpperCase()}</span>
                          {a.resolved&&<span style={{fontSize:10,color:C.ok,fontWeight:600}}>→ {a.assignedTo}</span>}
                        </div>
                        <div style={{fontSize:12,fontWeight:600,marginBottom:3}}>{a.scope}</div>
                        <div style={{fontSize:10,color:C.tm}}>{a.recommendation}</div>
                        {!a.resolved&&(
                          <div style={{display:"flex",gap:5,marginTop:8,flexWrap:"wrap"}}>
                            {(a.trades||[]).map(t=><button key={t} onClick={()=>setAmbs(p=>p.map(x=>x.id===a.id?{...x,resolved:true,assignedTo:t}:x))} style={mkBtn("ghost","sm")}>{t}</button>)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* SCOPE REPORT */}
            {mainView==="report" && selTrade && (
              <>
                <div style={{padding:"6px 16px",background:"#fff",borderBottom:`1px solid ${C.brd}`,display:"flex",alignItems:"center",gap:8}}>
                  <button onClick={()=>setMainView("export")} style={mkBtn("ghost","sm")}>{I.left} Back to Export</button>
                  <span style={{fontSize:12,color:C.tm}}>/ {selTrade.name}</span>
                </div>
                <ScopeReport trade={selTrade} items={items} trades={trades} fileBuffers={fileBuffers} onViewDrawing={viewDrawing}/>
              </>
            )}

            {/* DRAWING VIEWER */}
            {mainView==="drawing" && drawState && (
              <>
                <div style={{padding:"6px 16px",background:"#fff",borderBottom:`1px solid ${C.brd}`,display:"flex",alignItems:"center",gap:8}}>
                  <button onClick={()=>setMainView(selTrade?"report":"export")} style={mkBtn("ghost","sm")}>{I.left} Back</button>
                  <span style={{fontSize:12,color:C.tm}}>/ {drawState.fileName}</span>
                </div>
                <DrawingViewer
                  arrayBuf={drawState.buf}
                  pageNum={drawState.page}
                  findings={drawState.findings}
                  allItems={items}
                  trades={trades}
                  fileName={drawState.fileName}
                />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
