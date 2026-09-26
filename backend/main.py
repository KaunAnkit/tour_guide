"""
main.py — B.R. Ambedkar Museum Voice Tour Guide Backend
========================================================
FastAPI server with a single POST /converse endpoint that:
  1. Transcribes audio via Groq Whisper
  2. Sends transcript to an LLM with a search_artifacts tool (ChromaDB)
  3. Handles sequential tool_calls, re-calls the model, gets final answer
  4. Synthesises speech via Groq Orpheus TTS
  5. Returns JSON: {audio_url, text, transcript, artifacts}
"""

import json, os, pathlib, uuid, time, logging, math, wave, io, asyncio
from typing import Optional

import chromadb, httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── Config ──────────────────────────────────────────────────────────
load_dotenv(override=True)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE    = "https://api.groq.com/openai/v1"
WHISPER_MODEL = "whisper-large-v3-turbo"
CHAT_MODEL    = "openai/gpt-oss-120b"
TTS_MODEL     = "canopylabs/orpheus-v1-english"
TTS_VOICE     = "autumn"

BASE_DIR   = pathlib.Path(__file__).parent
AUDIO_DIR  = BASE_DIR / "audio_cache"
CHROMA_DIR = BASE_DIR / "chroma_db"
FRONTEND_DIR = BASE_DIR.parent / "frontend"

AUDIO_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tour_guide")

# ── ChromaDB ────────────────────────────────────────────────────────
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
try:
    collection = chroma_client.get_collection("ambedkar_museum")
    log.info(f"ChromaDB collection loaded — {collection.count()} documents")
except Exception:
    collection = None
    log.warning("ChromaDB collection 'ambedkar_museum' not found. Run seed_chroma.py first.")

# ── FastAPI app ─────────────────────────────────────────────────────
app = FastAPI(title="Ambedkar Museum Tour Guide")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Direct static routes for stylesheets and scripts
@app.get("/style.css")
async def get_style_css():
    return FileResponse(str(FRONTEND_DIR / "style.css"), media_type="text/css")

@app.get("/app.js")
async def get_app_js():
    return FileResponse(str(FRONTEND_DIR / "app.js"), media_type="application/javascript")

# Serve frontend static assets (exhibits, css, js)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend_static")

# Serve audio cache files
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio_cache")

# ── Persistent Groq HTTP client (connection pooling for low latency) ──
_shared_client: Optional[httpx.AsyncClient] = None

def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    key = os.getenv("GROQ_API_KEY", "").strip()
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            base_url=GROQ_BASE,
            headers={"Authorization": f"Bearer {key}"} if key else {},
            timeout=httpx.Timeout(45.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    else:
        if key:
            _shared_client.headers["Authorization"] = f"Bearer {key}"
    return _shared_client

# ── System prompt ──────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert voice tour guide at the Dr Ambedkar National Memorial.
Your purpose is to answer visitor questions about the life, works, speeches,
philosophy, and legacy of Dr. Bhimrao Ramji Ambedkar (1891–1956).

Multilingual Output Rules:
• MULTILINGUAL MATCHING: You MUST ALWAYS respond in the exact same language the visitor asks in.
• If the visitor asks in Hindi (in Devanagari script or Romanized Hindi/Hinglish), you MUST formulate your entire response in natural, respectful, conversational Hindi using Devanagari script.
• If the visitor asks in English, respond in English.
• For any other language, respond in that language.

Voice Guide Guidelines:
• Keep answers concise: exactly 2 to 3 engaging, spoken sentences (under 50 words) suitable for real-time speech synthesis.
• Use the search_artifacts tool to locate relevant photos, speeches, or articles from the museum collection.
• When citing an exhibit from search results, mention it naturally (in Hindi: e.g. "प्रदर्शनी की इस ऐतिहासिक तस्वीर में देखिए...", in English: e.g. "Notice the archival photo...").
• Never use markdown bolding, asterisks, bullet points, or lists — plain spoken sentences only.
• In English: always write out years as spoken words (e.g. write "nineteen twenty-seven" instead of "1927", "nineteen fifty-six" instead of "1956").
• In Hindi: write years and numbers naturally in Devanagari words or numerals (e.g. "उन्नीस सौ सत्ताईस" or "1927").
"""

# ── Tool definition for the LLM ───────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_artifacts",
            "description": (
                "Search the museum's collection of Ambedkar biography excerpts, "
                "speech transcripts, photo metadata, and scholarly articles. "
                "Returns relevant text chunks, image URLs, and article URLs. "
                "Query can be in English or Hindi."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query about Ambedkar's life, works, or exhibits in English or Hindi.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

# Hindi keyword mapping to assist ChromaDB English vector space
HINDI_KEYWORD_MAP = {
    "महाड": "Mahad Satyagraha 1927 Chavadar Tank water rights",
    "सत्याग्रह": "Mahad Satyagraha 1927",
    "संविधान": "Constitution drafting assembly 1949 draft committee",
    "दीक्षाभूमि": "Deekshabhoomi Nagpur 1956 Buddhist conversion",
    "बौद्ध": "Buddhism conversion Deekshabhoomi Nagpur 1956",
    "बचपन": "childhood early life Satara young Bhimrao 1901",
    "जन्म": "birth 1891 Mhow Madhya Pradesh early life",
    "शिक्षा": "education Columbia University London School Economics",
    "कोलंबिया": "Columbia University New York 1914 education",
    "लंदन": "London School Economics Gray's Inn",
    "भाषण": "speech Round Table Conference Annihilation of Caste",
    "जाति": "Annihilation of Caste social reform",
    "अंबेडकर": "Ambedkar biography life legacy",
}


# ── search_artifacts implementation ────────────────────────────────
def search_artifacts(query: str) -> dict:
    """Query ChromaDB and return structured results with Hindi-to-English expansion."""
    if collection is None:
        return {"text_chunks": [], "images": [], "articles": []}

    # Expand query if it contains known Hindi terms so English embeddings match accurately
    expanded_terms = [v for k, v in HINDI_KEYWORD_MAP.items() if k in query]
    search_query = f"{query} {' '.join(expanded_terms)}".strip() if expanded_terms else query

    results = collection.query(query_texts=[search_query], n_results=3)

    text_chunks = []
    images = []
    articles = []

    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i] if results["metadatas"] else {}
        doc_type = meta.get("type", "text")
        topic = meta.get("topic", "")

        text_chunks.append({"text": doc, "type": doc_type, "topic": topic})

        if doc_type == "photo" and meta.get("image_url"):
            images.append({
                "url": meta["image_url"],
                "title": topic.replace("_", " ").title(),
                "caption": doc[:120],
            })
        if doc_type == "article" and meta.get("url"):
            articles.append({
                "url": meta["url"],
                "title": topic.replace("_", " ").title(),
                "caption": doc[:120],
            })

    return {"text_chunks": text_chunks, "images": images, "articles": articles}


# ── Synthetic audio fallback generator (used only if Groq API fails) ─
def generate_voice_tone_wav(text: str, duration: float = 3.0) -> bytes:
    """Generate a clean, pleasant voice-like modulated WAV for orb pulsing."""
    sample_rate = 24000
    if text:
        duration = max(2.5, min(8.0, len(text) / 18.0))
    n_samples = int(sample_rate * duration)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            cadence = 0.4 + 0.6 * (0.5 * (1.0 + math.sin(2 * math.pi * 3.8 * t)))
            val = (
                0.55 * math.sin(2 * math.pi * 145 * t) +
                0.30 * math.sin(2 * math.pi * 580 * t) +
                0.15 * math.sin(2 * math.pi * 1600 * t)
            ) * cadence
            env = min(1.0, t * 6.0) * min(1.0, (duration - t) * 6.0)
            sample = int(val * env * 15000)
            sample = max(-32768, min(32767, sample))
            frames.extend(sample.to_bytes(2, byteorder="little", signed=True))
        wf.writeframes(frames)
    return buf.getvalue()



# ── PCM Extraction & Standard WAV Building ────────────────────
def extract_pcm_from_groq_wav(wav_bytes: bytes) -> bytes:
    """
    Extract raw 16-bit PCM from Groq Orpheus WAV.
    Groq always returns: RIFF(8) + fmt chunk(24) + LIST/INFO chunk(34) + data header(8) = 78 bytes
    The data chunk size is 0xFFFFFFFF (streaming), so PCM = wav_bytes[78:]
    Falls back to scanning for 'data' marker if the structure ever changes.
    """
    import struct
    # Fast path: check known Groq layout — data chunk starts at offset 70
    if len(wav_bytes) > 78 and wav_bytes[70:74] == b'data':
        return wav_bytes[78:]

    # Fallback: scan for 'data' chunk by walking RIFF chunks properly
    pos = 12  # skip RIFF header (4) + file size (4) + WAVE tag (4)
    while pos < len(wav_bytes) - 8:
        tag = wav_bytes[pos:pos+4]
        chunk_size = struct.unpack_from('<I', wav_bytes, pos+4)[0]
        if tag == b'data':
            pcm = wav_bytes[pos+8:]
            if pcm:
                return pcm
        if chunk_size == 0xFFFFFFFF or chunk_size == 0:
            break
        pos += 8 + chunk_size

    # Last resort: skip standard 44-byte header
    log.warning("Could not find data chunk, using 44-byte header skip")
    return wav_bytes[44:] if len(wav_bytes) > 44 else wav_bytes


def pcm_to_clean_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """
    Build a standard RIFF/WAVE container around raw 16-bit mono PCM.
    Guarantees correct headers, zero clicks, and zero static.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()




# ── Step 1: Transcribe audio via Whisper (ultra-fast) ──────────────
async def transcribe(audio_bytes: bytes, filename: str) -> str:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key.startswith("gsk_YOUR_KEY"):
        log.warning("No valid GROQ_API_KEY; using fallback inquiry.")
        return "Tell me about Dr. B.R. Ambedkar and the Mahad Satyagraha."

    log.info(f"Transcribing audio via Whisper on Groq ({len(audio_bytes)} bytes)…")
    client = get_shared_client()
    try:
        resp = await client.post(
            "/audio/transcriptions",
            data={"model": WHISPER_MODEL},
            files={"file": (filename, audio_bytes)},
        )
        if resp.status_code == 200:
            transcript = resp.json().get("text", "").strip()
            log.info(f"Whisper transcript: {transcript}")
            return transcript
        log.warning(f"Whisper returned {resp.status_code}: {resp.text}")
        return "Tell me about Dr. B.R. Ambedkar."
    except Exception as e:
        log.error(f"Whisper request exception: {e}")
        return "Tell me about Dr. B.R. Ambedkar."


# ── Step 2 & 3: Chat with sequential tool-calling ─────────────────
async def chat_with_tools(transcript: str) -> tuple[str, list[dict]]:
    """
    Send transcript to openai/gpt-oss-120b with search_artifacts tool.
    Handles sequential tool_calls, feeds results back, returns final text + artifacts.
    """
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key.startswith("gsk_YOUR_KEY"):
        # Fallback RAG if no key provided
        res = search_artifacts(transcript)
        artifacts = []
        for img in res.get("images", []):
            artifacts.append({"type": "photo", "title": img["title"], "url": img["url"], "caption": img["caption"]})
        for art in res.get("articles", []):
            artifacts.append({"type": "article", "title": art["title"], "url": art["url"], "caption": art["caption"]})
        chunks = res.get("text_chunks", [])
        ans = chunks[0]["text"] if chunks else "Dr. B.R. Ambedkar was the chief architect of the Indian Constitution."
        return ans, artifacts

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": transcript},
    ]
    collected_artifacts = []
    max_rounds = 4

    client = get_shared_client()
    for _ in range(max_rounds):
        payload = {
            "model": CHAT_MODEL,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0.5,
            "max_tokens": 512,
        }
        log.info(f"Chat request → {CHAT_MODEL}")
        try:
            resp = await client.post("/chat/completions", json=payload)
        except Exception as e:
            log.error(f"Chat request failed: {e}")
            break

        if resp.status_code != 200:
            log.error(f"Chat error {resp.status_code}: {resp.text}")
            break

        body = resp.json()
        choice = body["choices"][0]
        msg = choice["message"]

        if msg.get("tool_calls"):
            messages.append(msg)
            # Sequential tool handling
            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except Exception:
                    fn_args = {"query": transcript}
                log.info(f"Sequential tool call: {fn_name}({fn_args})")

                if fn_name == "search_artifacts":
                    result = search_artifacts(fn_args.get("query", transcript))
                    for img in result.get("images", []):
                        collected_artifacts.append({
                            "type": "photo",
                            "title": img["title"],
                            "url": img["url"],
                            "caption": img["caption"],
                        })
                    for art in result.get("articles", []):
                        collected_artifacts.append({
                            "type": "article",
                            "title": art["title"],
                            "url": art["url"],
                            "caption": art["caption"],
                        })
                else:
                    result = {"error": f"Unknown tool: {fn_name}"}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })
            continue

        answer = msg.get("content", "") or ""
        if answer.strip():
            return answer.strip(), collected_artifacts

        # If model returned no tool calls and empty content, nudge it once to reply
        messages.append({"role": "user", "content": "Please provide your concise voice tour guide response in the requested language."})

    # Fallback if rounds exhausted or empty
    res = search_artifacts(transcript)
    for img in res.get("images", []):
        collected_artifacts.append({"type": "photo", "title": img["title"], "url": img["url"], "caption": img["caption"]})
    for art in res.get("articles", []):
        collected_artifacts.append({"type": "article", "title": art["title"], "url": art["url"], "caption": art["caption"]})
    chunks = res.get("text_chunks", [])
    if is_hindi_text(transcript):
        ans = "डॉक्टर भीमराव अंबेडकर भारतीय संविधान के मुख्य वास्तुकार और महान समाज सुधारक थे।"
    else:
        ans = chunks[0]["text"] if chunks else "Dr. B.R. Ambedkar was a profound jurist, economist, and social reformer."
    return ans, collected_artifacts


# ── Year-to-spoken-words converter for natural TTS pronunciation ──
def _convert_years_to_words(text: str) -> str:
    """Convert 4-digit years (1800-2099) to spoken-word form for natural TTS.
    E.g. '1927' → 'nineteen twenty-seven', '1956' → 'nineteen fifty-six'.
    """
    import re

    ones = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
            'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
            'seventeen', 'eighteen', 'nineteen']
    tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']

    def two_digit_to_words(n: int) -> str:
        if n == 0:
            return 'hundred'
        if n < 20:
            return ones[n]
        t, o = divmod(n, 10)
        return f"{tens[t]}-{ones[o]}" if o else tens[t]

    def year_to_words(match):
        year_str = match.group(0)
        year = int(year_str)
        if year < 1800 or year > 2099:
            return year_str
        century = year // 100
        remainder = year % 100
        if remainder == 0:
            return f"{two_digit_to_words(century)} hundred"
        first = two_digit_to_words(century)
        second = two_digit_to_words(remainder)
        if remainder < 10:
            return f"{first} oh {second}"
        return f"{first} {second}"

    return re.sub(r'\b(1[89]\d{2}|20\d{2})\b', year_to_words, text)


def is_hindi_text(text: str) -> bool:
    """Return True if text contains Devanagari characters."""
    return any("\u0900" <= ch <= "\u097f" for ch in text)


async def synthesise_hindi_speech(text: str) -> Optional[str]:
    """Synthesise natural, respectful Hindi voice via Edge TTS hi-IN-MadhurNeural."""
    import edge_tts
    try:
        fname = f"{uuid.uuid4().hex[:12]}.mp3"
        fpath = AUDIO_DIR / fname
        communicate = edge_tts.Communicate(text, "hi-IN-MadhurNeural")
        await communicate.save(str(fpath))
        log.info(f"Synthesized Hindi speech via Edge TTS: {fpath.name}")
        return f"/audio/{fname}"
    except Exception as e:
        log.error(f"Edge TTS Hindi failed: {e}")
        try:
            from gtts import gTTS
            fname = f"{uuid.uuid4().hex[:12]}.mp3"
            fpath = AUDIO_DIR / fname
            tts = gTTS(text=text, lang="hi")
            tts.save(str(fpath))
            log.info(f"Synthesized Hindi speech via gTTS fallback: {fpath.name}")
            return f"/audio/{fname}"
        except Exception as ge:
            log.error(f"gTTS fallback failed: {ge}")
            audio_bytes = generate_voice_tone_wav(text)
            fname = f"{uuid.uuid4().hex[:12]}.wav"
            fpath = AUDIO_DIR / fname
            fpath.write_bytes(audio_bytes)
            return f"/audio/{fname}"


# ── Step 4: Low-Latency Speech Synthesis via Groq Orpheus / Edge TTS ─────────
async def synthesise_speech(text: str) -> Optional[str]:
    """
    Convert text to speech:
    - If Hindi: Synthesize via Edge TTS (hi-IN-MadhurNeural) with natural native accent.
    - If English: Synthesize via Groq Orpheus with ultra-low latency (<2s).
    """
    if not text:
        return None

    # Clean text to strip any asterisks, hashes, brackets that confuse speech synthesis
    clean_text = text.replace("*", "").replace("#", "").replace("`", "").replace('"', "")
    clean_text = " ".join(clean_text.split())

    # Detect Hindi and route to dedicated Hindi TTS
    if is_hindi_text(clean_text):
        return await synthesise_hindi_speech(clean_text)

    # For English: convert years to spoken words (e.g. 1927 -> nineteen twenty-seven)
    clean_text = _convert_years_to_words(clean_text)

    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key.startswith("gsk_YOUR_KEY"):
        audio_bytes = generate_voice_tone_wav(clean_text)
        fname = f"{uuid.uuid4().hex[:12]}.wav"
        fpath = AUDIO_DIR / fname
        fpath.write_bytes(audio_bytes)
        return f"/audio/{fname}"

    chunks = _chunk_text(clean_text, max_len=500)
    log.info(f"Synthesising Orpheus TTS: {len(chunks)} chunk(s) (total {len(clean_text)} chars)")

    client = get_shared_client()

    async def fetch_chunk(chunk_str: str) -> Optional[bytes]:
        payload = {
            "model": TTS_MODEL,
            "input": chunk_str,
            "voice": TTS_VOICE,
            "response_format": "wav",
        }
        t0 = time.time()
        try:
            resp = await client.post("/audio/speech", json=payload)
            if resp.status_code == 200:
                elapsed = time.time() - t0
                pcm = extract_pcm_from_groq_wav(resp.content)
                log.info(f"TTS chunk ({len(chunk_str)} chars) in {elapsed:.2f}s, pcm={len(pcm)} bytes")
                return pcm
            else:
                log.warning(f"Groq TTS error {resp.status_code}: {resp.text}")
                return None
        except Exception as e:
            log.error(f"Groq TTS exception: {e}")
            return None

    if len(chunks) == 1:
        all_pcm = await fetch_chunk(chunks[0])
        all_pcm = all_pcm if all_pcm else b""
    else:
        results = await asyncio.gather(*[fetch_chunk(c) for c in chunks])
        all_pcm = b"".join([r for r in results if r])

    if not all_pcm:
        log.warning("Groq TTS produced no PCM audio, using tone fallback.")
        clean_wav = generate_voice_tone_wav(clean_text)
    else:
        clean_wav = pcm_to_clean_wav(all_pcm, sample_rate=24000)

    fname = f"{uuid.uuid4().hex[:12]}.wav"
    fpath = AUDIO_DIR / fname
    fpath.write_bytes(clean_wav)
    log.info(f"Clean WAV saved: {fpath.name} ({len(clean_wav)} bytes)")
    return f"/audio/{fname}"


def _chunk_text(text: str, max_len: int = 500) -> list[str]:
    """Split text into sentence-aligned chunks under max_len."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""
    for s in sentences:
        if not s.strip():
            continue
        if len(current) + len(s) + 1 <= max_len:
            current = (current + " " + s).strip()
        else:
            if current:
                chunks.append(current)
            while len(s) > max_len:
                chunks.append(s[:max_len])
                s = s[max_len:]
            current = s
    if current:
        chunks.append(current)
    return chunks or [text[:max_len]]


# ── Main endpoint ──────────────────────────────────────────────────
@app.post("/converse")
async def converse(
    audio: Optional[UploadFile] = File(None),
    query: Optional[str] = Form(None)
):
    # If audio is supplied, transcribe it
    if audio is not None:
        audio_bytes = await audio.read()
        if len(audio_bytes) >= 100:
            transcript = await transcribe(audio_bytes, audio.filename or "recording.webm")
        elif query:
            transcript = query
        else:
            transcript = "Tell me about Dr. B.R. Ambedkar."
    elif query:
        transcript = query
    else:
        transcript = "Tell me about Dr. B.R. Ambedkar."

    if not transcript.strip():
        return JSONResponse({
            "audio_url": None,
            "text": "I didn't catch that. Could you please tap and ask again?",
            "transcript": "",
            "artifacts": [],
        })

    log.info(f"Active Query/Transcript: {transcript}")

    # 2 & 3. Chat + sequential tool calls with ChromaDB
    answer_text, artifacts = await chat_with_tools(transcript)
    log.info(f"Tour Guide Answer: {answer_text[:120]}…")

    # 4. Synthesise speech via Orpheus TTS
    audio_url = await synthesise_speech(answer_text)

    # 5. Return JSON payload
    return JSONResponse({
        "audio_url": audio_url,
        "text": answer_text,
        "transcript": transcript,
        "artifacts": artifacts,
    })


# ── Serve frontend index at root ───────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# ── Health check ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "chroma_docs": collection.count() if collection else 0,
        "groq_key_set": bool(GROQ_API_KEY),
    }


# ── Cleanup ─────────────────────────────────────────────────────────
@app.on_event("shutdown")
async def shutdown():
    await groq.aclose()
    # Clean up old audio files (>1 hour)
    cutoff = time.time() - 3600
    for f in list(AUDIO_DIR.glob("*.wav")) + list(AUDIO_DIR.glob("*.mp3")):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
