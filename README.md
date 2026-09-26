# B.R. Ambedkar Museum — Voice Tour Guide

A voice-guided tour app for the Dr. B.R. Ambedkar National Memorial kiosk. Visitors can ask questions by voice and browse source-backed exhibit records.

## Architecture

```
frontend/          Vanilla HTML / CSS / JS
  index.html       Single-page app
  style.css        Museum visual system, kiosk layout, and scrolling
  app.js           Mic capture, Web Audio orb, and content cards

backend/           Python FastAPI
  main.py          /converse endpoint (Whisper → LLM → Orpheus TTS)
  artifacts.py     Artifact IDs, Markdown context, and structured related data
  seed_chroma.py   Seed existing and Markdown-derived content into ChromaDB
  requirements.txt Python dependencies
  .env.example     API key template
```

Exhibit Markdown remains the source of truth for QR exhibit context. Add optional JSON under `### Related content for UI (speeches, locations, books)` using the `related_speeches`, `related_locations`, and `related_books` arrays. `seed_chroma.py` keeps the existing corpus and adds searchable Markdown chunks tagged with the stable `artifact_id`; the backend parses related card data separately and returns it directly to the UI.

## Quick Start

### 1. Set up the backend

```bash
cd backend
pip install -r requirements.txt

# Copy and edit .env
cp .env.example .env
# → paste your Groq API key into .env

# Seed the vector database
python seed_chroma.py

# Start the server
uvicorn main:app --reload --port 8000
```

### 2. Open the app

Navigate to **http://localhost:8000** — the backend serves the frontend.

### 3. Use it

- **Tap the orb** to start recording
- **Tap again** to stop — your question is sent to the server
- The orb pulses with your mic amplitude (green) and with the guide's
  voice (blue) during playback
- Photo, speech, location, and book cards appear below the transcript when source data exists
- Long exhibit content scrolls normally with touch or stylus; mouse drags on non-interactive areas scroll during development
- Tap a photo preview to open its complete image in the full-screen viewer

## API

### `POST /converse`

**Request:** `multipart/form-data` with an `audio` file field.

**Response:**
```json
{
  "audio_url": "/audio/abc123.wav",
  "text": "Ambedkar was born on 14 April 1891…",
  "transcript": "When was Ambedkar born?",
  "artifacts": [
    {
      "type": "photo",
      "title": "Young Ambedkar",
      "url": "/static/exhibits/young_ambedkar.jpg",
      "caption": "Photograph: Young Bhimrao at age 10…"
    }
  ],
  "related_speeches": [],
  "related_locations": [],
  "related_books": []
}
```

### `GET /health`

Returns `{ status, chroma_docs, groq_key_set }`.

## Requirements

- Python 3.10+
- A [Groq API key](https://console.groq.com) (free tier works)
- A modern browser with microphone access (Chrome/Edge recommended)
