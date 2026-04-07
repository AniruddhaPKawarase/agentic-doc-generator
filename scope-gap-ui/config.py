"""
Configuration — reads from environment variables with sensible defaults.
"""
import os

API_BASE: str = os.environ.get("SCOPE_API_BASE", "http://54.197.189.113:8003")
REQUEST_TIMEOUT: int = int(os.environ.get("SCOPE_REQUEST_TIMEOUT", "300"))
GENERATE_TIMEOUT: int = int(os.environ.get("SCOPE_GENERATE_TIMEOUT", "600"))

PROJECTS = [
    {"id": "PRJ-001", "project_id": 7276, "name": "450-460 JR PKWY Phase II",
     "loc": "Nashville, TN", "pm": "Smith Gee Studio", "status": "Active",
     "type": "Residential & Garage", "prog": 62},
    {"id": "PRJ-002", "project_id": 7298, "name": "AVE Horsham Multi-Family",
     "loc": "Horsham, PA", "pm": "Bernardon Design", "status": "Active",
     "type": "Multi-Family", "prog": 38},
    {"id": "PRJ-003", "project_id": 7212, "name": "HSB Potomac Senior Living",
     "loc": "Potomac, MD", "pm": "Vessel Architecture", "status": "Active",
     "type": "Senior Living", "prog": 45},
    {"id": "PRJ-004", "project_id": 7222, "name": "Metro Transit Hub",
     "loc": "Chicago, IL", "pm": "James Wilson", "status": "On-Hold",
     "type": "Infrastructure", "prog": 15},
    {"id": "PRJ-005", "project_id": 7223, "name": "Greenfield Data Center",
     "loc": "Phoenix, AZ", "pm": "Tom Davis", "status": "Completed",
     "type": "Industrial", "prog": 100},
]

TRADE_COLOR_PALETTE = [
    "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
    "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
    "#14B8A6", "#D97706", "#DC2626", "#7C3AED", "#DB2777",
    "#0891B2", "#65A30D", "#EA580C", "#4F46E5", "#0D9488",
    "#B45309", "#BE123C", "#6D28D9",
]

STATUS_CONFIG = {
    "Active":    {"bg": "#DCFCE7", "text": "#166534", "dot": "#22C55E"},
    "On-Hold":   {"bg": "#FEF3C7", "text": "#92400E", "dot": "#F59E0B"},
    "Completed": {"bg": "#F1F5F9", "text": "#475569", "dot": "#94A3B8"},
}

AGENTS = [
    {"name": "RFI Agent",       "icon": "❓", "desc": "Manage RFIs and queries",          "page": None},
    {"name": "Submittal Agent", "icon": "📋", "desc": "Track submittal packages",          "page": None},
    {"name": "Drawings Agent",  "icon": "📐", "desc": "Scope gap analysis on drawings",   "page": "workspace"},
    {"name": "Spec Agent",      "icon": "📄", "desc": "Specification review & gaps",       "page": None},
    {"name": "BIM Planner",     "icon": "🏗️", "desc": "BIM coordination & clash detection","page": None},
    {"name": "Meeting Agent",   "icon": "🗓️", "desc": "Meeting summaries & action items",  "page": None},
]

MOCK_TRADES = [
    "Electrical", "Plumbing", "HVAC", "Structural", "Concrete",
    "Fire Sprinkler", "Roofing & Waterproofing", "Framing Drywall & Insulation",
    "Glass & Glazing", "Painting & Coatings",
]

MOCK_DRAWINGS = {
    "Architectural": ["A-001 Site Plan", "A-101 Floor Plan L1", "A-201 Elevations"],
    "Structural":    ["S-001 Foundation Plan", "S-101 Framing Plan"],
    "Electrical":    ["E-001 Power Plan", "E-101 Lighting Plan"],
    "Plumbing":      ["P-001 Plumbing Plan", "P-101 Riser Diagram"],
    "Mechanical":    ["M-001 HVAC Layout", "M-101 Ductwork Plan"],
}
