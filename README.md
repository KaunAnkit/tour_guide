# B. R. Ambedkar National Memorial — Voice Tour Guide

A single-page, touch-first museum kiosk for exploring Dr. B. R. Ambedkar's life, writings, speeches and legacy. The frontend is vanilla HTML, CSS and JavaScript; the existing FastAPI service provides voice transcription, archive retrieval, answers and speech audio.

## Project Layout

```text
frontend/
  index.html                 Kiosk sections and preserved legacy guide markup
  style.css                  Kiosk design system and responsive touch layout
  app.js                     Kiosk interactions and existing voice client
  data/kiosk-content.js      Local exhibit, book, speech, media and topic records
  assets/                    Memorial marks and homepage-specific artwork
  exhibits/                  Existing local exhibit photographs

backend/
  main.py                    FastAPI application and POST /converse
  artifacts.py               Artifact context and structured related content
  seed_chroma.py             Build/update the ChromaDB archive
  requirements.txt           Python backend dependencies
  .env.example               API key template

qr_data/                     Exhibit source context in Markdown
```

## Run Locally

Use Python 3.10 or newer.

```powershell
cd backend
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Add a Groq API key to `backend/.env` as `GROQ_API_KEY=...`. Then seed the archive and start the server:

```powershell
python seed_chroma.py
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000/](http://localhost:8000/). FastAPI serves the frontend and API from the same origin. Microphone access requires a modern browser and is generally available on `localhost` or HTTPS.

## Kiosk Experience

The `/` route is one vertically scrollable kiosk, with a sticky section header. Visitors can browse the welcome, Ask the Guide, exhibits, books, speeches and interviews, historical media, and connected topics without entering the preserved legacy guide layout.

- **Tap to Speak** uses the existing microphone recording and audio-amplitude visualization.
- **Suggested questions** and connected-topic controls send text queries through the same `/converse` endpoint.
- Answers, the returned transcript, available related records, and synthesized speech are shown in the kiosk interface.
- Exhibit cards open inline details. **Ask About This** moves to the guide; the backend does not receive a separate exhibit-context parameter.
- Book links and speech recordings are intentionally pending until verified URLs or local files are added.
- After about 60 seconds without interaction, the kiosk returns to its welcome attract screen. Recording, answer playback, open viewers and active interaction defer the reset.
- **Start Over** stops playback/recording, clears the current answer and viewers, and returns to the top.

The frontend adds no JavaScript framework or package dependencies. Its language selector localizes the main interface and suggested questions in English, Hindi and Marathi; the archive answer language follows the submitted question or speech transcription.

## Add Local Content

Edit `frontend/data/kiosk-content.js`; no backend changes are needed for these static kiosk records.

- **Exhibits:** `title`, `description`, `image`, and `query`. Use paths to existing files under `/static/` for images.
- **Books:** `title`, `author`, optional `year`, `cover`, `description`, and `url`. Leave `cover` and `url` empty until a verified cover and source are available. Local PDFs can be placed under `frontend/` and referenced via their `/static/...pdf` URL.
- **Speeches:** `title`, `speaker`, optional `date`, `duration`, `thumbnail`, `video`, `description`, `transcript`, and `segments`. `video` supports a verified YouTube URL or a local media URL. Empty media fields show a placeholder rather than a fabricated link.
- **Historical media:** `type`, `title`, `image`, `caption`, and optional `source`. The existing exhibit photographs are already used in the demo gallery.
- **Connections:** groups of topic labels. Selecting a topic asks the existing guide about it; these records are static and are not a dynamically generated knowledge graph.

Do not add unverified archival attribution, dates, source links or recordings. Provide a real source URL or local asset before enabling a record for public use.

## API

### `POST /converse`

The frontend submits either a recorded `audio` file or a text `query` as `multipart/form-data`. The existing backend transcribes audio when supplied, searches the archive, and returns its answer and available related records. This endpoint and its processing flow are unchanged.

Example response shape:

```json
{
  "audio_url": "/audio/example.wav",
  "text": "Archive-grounded answer text",
  "transcript": "Visitor question",
  "artifacts": [],
  "related_speeches": [],
  "related_locations": [],
  "related_books": []
}
```

### `GET /health`

Reports service status, ChromaDB document count and whether a Groq API key is configured.

## Archive Sources

Exhibit Markdown under `qr_data/` remains the source of truth for QR exhibit context. Optional structured UI records can be added under `### Related content for UI (speeches, locations, books)` using `related_speeches`, `related_locations`, and `related_books`. `seed_chroma.py` indexes supported Markdown content and preserves stable artifact IDs.

## Backend Dependencies

`backend/requirements.txt` contains the Python server dependencies, including Edge TTS for Hindi synthesis and gTTS as its fallback. The browser frontend itself has no install step.