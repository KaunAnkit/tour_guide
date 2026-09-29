# B.R. Ambedkar Museum — Voice Tour Guide

A voice-only tour-guide web app for a handheld museum device. Ask questions
about Dr. B.R. Ambedkar's life, speeches, and legacy using your voice.

## Architecture

```
frontend/          Vanilla HTML / CSS / JS
  index.html       Single-page app
  style.css        Design system (navy/gold, glassmorphism)
  app.js           Mic capture, Web Audio orb, artifact cards

backend/           Python FastAPI
  main.py          /converse endpoint (Whisper → LLM → Orpheus TTS)
  seed_chroma.py   Populate ChromaDB with museum content
  requirements.txt Python dependencies
  .env.example     API key template
```

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

## Deploy to Render

This repository includes a `render.yaml` Blueprint for a single Render Web Service. The FastAPI backend serves the frontend, exhibit images, QR data, and API from the same URL.

1. Push the repository to GitHub or GitLab.
2. In Render, choose **New +** → **Blueprint** and select the repository.
3. Render will read `render.yaml`. When prompted, enter your `GROQ_API_KEY` as a secret environment variable.
4. Deploy and open the generated `https://...onrender.com` URL. Check `https://...onrender.com/health` first.

The service uses the checked-in ChromaDB files in `backend/chroma_db`. Render's local filesystem is ephemeral, but generated audio is only a temporary cache and is recreated when needed. If you create or change the vector database, commit the updated `backend/chroma_db` files and redeploy.

For a manual Web Service instead, use:

- Build command: `pip install -r backend/requirements.txt`
- Start command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Environment variable: `GROQ_API_KEY` (secret)

### 3. Use it

- **Tap the orb** to start recording
- **Tap again** to stop — your question is sent to the server
- The orb pulses with your mic amplitude (green) and with the guide's
  voice (blue) during playback
- Artifact cards (photos, articles) slide in below the transcript

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
  ]
}
```

### `GET /health`

Returns `{ status, chroma_docs, groq_key_set }`.

## Requirements

- Python 3.10+
- A [Groq API key](https://console.groq.com) (free tier works)
- A modern browser with microphone access (Chrome/Edge recommended)
