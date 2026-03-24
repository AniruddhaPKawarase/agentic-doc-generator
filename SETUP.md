# Construction Intelligence Agent - Setup Guide

## 1. Prerequisites

- Python 3.10+
- OpenAI API key
- Access to:
  - `https://mongo.ifieldsmart.com/api/drawingText/uniqueCsi?projectId=<id>`
  - `https://mongo.ifieldsmart.com/api/drawingText/uniqueText?projectId=<id>`
  - `https://mongo.ifieldsmart.com/api/drawingText/uniqueTrades?projectId=<id>`
- Optional: Redis for shared cache

## 2. Install

```bash
cd construction-intelligence-agent
python -m venv .ciaenv

# Windows
.ciaenv\Scripts\activate

pip install -r requirements.txt
```

## 3. Configure

```bash
copy .env.example .env
```

Set these in `.env`:

```ini
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4.1-mini
API_BASE_URL=https://mongo.ifieldsmart.com
CSI_DIVISIONS_PATH=/api/drawingText/uniqueCsi
UNIQUE_TEXTS_PATH=/api/drawingText/uniqueText
UNIQUE_TRADES_PATH=/api/drawingText/uniqueTrades
DRAWING_DATA_PATH=
```

`DRAWING_DATA_PATH` can stay empty if you only have the 3 unique endpoints.

## 4. Run

```bash
python main.py
```

Open:

- UI: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## 5. Test the pipeline

1. Load project context:
```bash
curl http://localhost:8000/api/projects/7276/context
```
2. Ask generation query:
```bash
curl -X POST http://localhost:8000/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"project_id\":7276,\"query\":\"Create a scope for plumbing\",\"generate_document\":true}"
```
3. Download file with returned `document.download_url`.
