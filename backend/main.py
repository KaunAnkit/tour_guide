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

import json, os, pathlib, uuid, time, logging, math, wave, io, asyncio, re, unicodedata
from typing import Optional

import chromadb, httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from artifacts import (
    artifact_payload,
    build_exhibit_system_prompt,
    get_artifact,
)

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
QR_DATA_DIR  = BASE_DIR.parent / "qr_data"
CONTENT_DIR = BASE_DIR.parent / "content"

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

@app.get("/exhibit.css")
async def get_exhibit_css():
    return FileResponse(str(FRONTEND_DIR / "exhibit.css"), media_type="text/css")

@app.get("/exhibit.js")
async def get_exhibit_js():
    return FileResponse(str(FRONTEND_DIR / "exhibit.js"), media_type="application/javascript")

# Serve QR artifact images and context assets
if QR_DATA_DIR.is_dir():
    app.mount("/qr_data", StaticFiles(directory=str(QR_DATA_DIR)), name="qr_data")

# Serve only the repository's intended archival content directory.
if CONTENT_DIR.is_dir():
    app.mount("/content", StaticFiles(directory=str(CONTENT_DIR)), name="archival_content")

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
• Answer using the retrieved archival evidence below; do not rely on unsupported general knowledge when relevant evidence exists.
• Use only sources that directly address the question. Prefer relevant books and collected writings, then relevant speech/interview transcripts, then exhibit records and media metadata. Relevance comes before source type.
• Whisper transcripts and informal Hindi/Hinglish may contain recognition errors. Interpret the visitor's intent before deciding that no archive source exists.
• If the supplied passages do not directly answer the question, call search_artifacts with concise, corrected or expanded archive queries before replying. You may make several sequential searches.
• If the archive evidence does not establish an answer, say so briefly instead of guessing.
• You may quote only a short, exact passage copied from the retrieved evidence. Never invent a quotation or put a paraphrase in quotation marks.
• Never use markdown bolding, asterisks, bullet points, or lists — plain spoken sentences only.
• In English: always write out years as spoken words (e.g. write "nineteen twenty-seven" instead of "1927", "nineteen fifty-six" instead of "1956").
• In Hindi: write years and numbers naturally in Devanagari words or numerals (e.g. "उन्नीस सौ सत्ताईस" or "1927").
"""

ARCHIVE_RELEVANCE_DISTANCE = 0.60
ARCHIVE_RESULT_COUNT = 5
ARCHIVE_MAX_SEARCH_QUERIES = 4
ARCHIVE_MAX_PROMPT_CHUNKS = 5

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
    "पढ़ाई": "Ambedkar higher education Columbia University London School Economics",
    "पढाई": "Ambedkar higher education Columbia University London School Economics",
    "पढ़ाई खत्म": "Ambedkar completed higher education Columbia University London School Economics",
    "कहां": "Ambedkar education where studied Columbia University London School Economics",
    "कहाँ": "Ambedkar education where studied Columbia University London School Economics",
    "कहां पे": "Ambedkar education where studied Columbia University London School Economics",
    "कहाँ पे": "Ambedkar education where studied Columbia University London School Economics",
    "कोलंबिया": "Columbia University New York 1914 education",
    "लंदन": "London School Economics Gray's Inn",
    "भाषण": "speech Round Table Conference Annihilation of Caste",
    "जाति": "Annihilation of Caste social reform",
    "अंबेडकर": "Ambedkar biography life legacy",
}

HINDI_ANSWER_KEYWORD_MAP = {
    "कोलंबिया": "Columbia University",
    "विश्वविद्यालय": "University",
    "न्यूयॉर्क": "New York",
    "लंदन": "London",
    "इकोनॉमिक्स": "Economics",
    "अर्थशास्त्र": "Economics",
    "ग्रे": "Gray",
    "इन": "Inn",
}


def normalize_archive_queries(query: str) -> list[str]:
    """Keep the visitor's wording while adding concise corrections and archive terms."""
    normalized = unicodedata.normalize("NFKC", query or "")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    corrected = re.sub(
        r"\byear\s+a\s+mid[- ]?care\b|\ba\s+mid[- ]?care\b",
        "Ambedkar",
        normalized,
        flags=re.IGNORECASE,
    )

    variants: list[str] = []

    def add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip()
        if value and value.casefold() not in {item.casefold() for item in variants}:
            variants.append(value)

    add(query)
    add(normalized)
    add(corrected)

    folded = f"{normalized} {corrected}".casefold()
    mapped_terms = list(dict.fromkeys(
        value for phrase, value in HINDI_KEYWORD_MAP.items()
        if phrase.casefold() in folded
    ))
    if re.search(r"\b(padhai|padhaai|parhai|kahan|kaha)\b", folded):
        mapped_terms.append("Ambedkar education Columbia University London School of Economics")
    if mapped_terms:
        add(" ".join(mapped_terms))

    education_query = re.search(
        r"\b(education|educated|stud\w*|school|university|college|degree|padhai|padhaai|parhai)\b",
        folded,
    ) or any("education" in value.casefold() for value in mapped_terms)
    if education_query:
        add("Ambedkar higher education Columbia University New York London School of Economics")
    if re.search(r"\b(rupee|currency|monetary|exchange)\b|problem of the rupee", folded):
        add("The Problem of the Rupee Ambedkar currency rupee gold silver monetary policy")
    if re.search(r"\b(buddha|dhamma|buddhism)\b", folded):
        add("The Buddha and His Dhamma Ambedkar Buddha Dhamma Buddhism")
    if re.search(r"\b(constitution|drafting|draft|assembly)\b|संविधान", folded):
        add("Ambedkar Constitution drafting Drafting Committee Constituent Assembly")

    return variants[:ARCHIVE_MAX_SEARCH_QUERIES]


# ── search_artifacts implementation ────────────────────────────────
def search_artifacts(query: str) -> dict:
    """Query ChromaDB and return structured results with Hindi-to-English expansion."""
    if collection is None:
        return {"text_chunks": [], "images": [], "articles": [], "sources": []}

    # Expand query if it contains known Hindi terms so English embeddings match accurately
    expanded_terms = [v for k, v in HINDI_KEYWORD_MAP.items() if k in query]
    search_query = f"{query} {' '.join(expanded_terms)}".strip() if expanded_terms else query

    result_count = min(ARCHIVE_RESULT_COUNT, collection.count())
    if not result_count:
        return {"text_chunks": [], "images": [], "articles": [], "sources": []}

    results = collection.query(
        query_texts=[search_query],
        n_results=result_count,
        include=["documents", "metadatas", "distances"],
    )

    text_chunks = []
    images = []
    articles = []
    sources = []

    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i] if results["metadatas"] else {}
        distance = results["distances"][0][i] if results["distances"] else None
        if distance is not None and distance > ARCHIVE_RELEVANCE_DISTANCE:
            continue

        doc_type = meta.get("type", "text")
        topic = meta.get("topic", "")
        record_id = results["ids"][0][i]
        source = {
            "record_id": record_id,
            "type": doc_type,
            "title": meta.get("document_title") or topic.replace("_", " ").title(),
            "source_file": meta.get("source_file"),
            "source_path": meta.get("source_path"),
            "page_number": meta.get("page_number"),
            "speaker": meta.get("speaker"),
            "timestamp": meta.get("timestamp"),
            "source_url": meta.get("source_url") or meta.get("url"),
            "excerpt": doc[:280].strip(),
            "distance": distance,
        }

        text_chunks.append({
            "record_id": record_id,
            "text": doc,
            "type": doc_type,
            "topic": topic,
            "source": source,
        })
        sources.append(source)

        if doc_type == "photo" and meta.get("image_url"):
            images.append({
                "record_id": record_id,
                "url": meta["image_url"],
                "title": topic.replace("_", " ").title(),
                "caption": doc[:120],
            })
        if doc_type == "article" and meta.get("url"):
            articles.append({
                "record_id": record_id,
                "url": meta["url"],
                "title": topic.replace("_", " ").title(),
                "caption": doc[:120],
            })

    return {"text_chunks": text_chunks, "images": images, "articles": articles, "sources": sources}


def _format_archive_evidence(text_chunks: list[dict]) -> str:
    if not text_chunks:
        return "No sufficiently relevant archival passage was retrieved. Do not answer from memory."

    passages = []
    for index, chunk in enumerate(text_chunks[:ARCHIVE_MAX_PROMPT_CHUNKS], start=1):
        source = chunk.get("source") or {}
        details = [
            f"Record ID: {source.get('record_id') or chunk.get('record_id', '')}",
            f"Type: {source.get('type') or chunk.get('type', '')}",
            f"Title: {source.get('title') or chunk.get('topic', '')}",
        ]
        if source.get("source_file") or source.get("source_path"):
            details.append(f"File: {source.get('source_file') or source.get('source_path')}")
        if source.get("page_number") is not None:
            details.append(f"Page: {source['page_number']}")
        if source.get("speaker"):
            details.append(f"Speaker: {source['speaker']}")
        if source.get("timestamp"):
            details.append(f"Timestamp: {source['timestamp']}")
        passages.append(
            f"[Source {index}; {'; '.join(details)}]\n{chunk.get('text', '')[:700]}"
        )
    return "Retrieved archival evidence (use only passages relevant to the question):\n\n" + "\n\n".join(passages)


def _remove_unverified_quotes(answer: str, evidence_texts: list[str]) -> str:
    normalized_sources = [re.sub(r"\s+", " ", text) for text in evidence_texts]
    quote_pattern = re.compile(r'"([^"\n]+)"|“([^”\n]+)”|‘([^’\n]+)’|(?<!\w)\'([^\'\n]+)\'(?!\w)')

    def keep_only_verbatim_quotes(match: re.Match) -> str:
        quoted_text = next((group for group in match.groups() if group is not None), "")
        normalized_quote = re.sub(r"\s+", " ", quoted_text)
        if normalized_quote and any(normalized_quote in source for source in normalized_sources):
            return match.group(0)
        return quoted_text

    return quote_pattern.sub(keep_only_verbatim_quotes, answer)


def _select_supporting_sources(
    question: str,
    answer: str,
    sources: list[dict],
    evidence_chunks: list[dict],
    query_context: str = "",
) -> list[dict]:
    stop_words = {
        "about", "after", "also", "ambedkar", "and", "are", "been", "before",
        "being", "between", "both", "could", "did", "does", "from", "have",
        "here", "higher", "his", "into", "just", "more", "most", "new", "only", "other", "over",
        "that", "their", "them", "then", "there", "these", "they", "this", "those",
        "through", "under", "very", "what", "when", "where", "which", "while",
        "with", "would", "your", "about", "the", "was", "were", "will", "would",
    }

    def terms(value: str) -> set[str]:
        return {
            word for word in re.findall(r"[a-z0-9]+", value.lower())
            if len(word) > 2 and word not in stop_words
        }

    answer_context = answer
    if is_hindi_text(answer):
        answer_context += " " + " ".join(
            english for hindi, english in HINDI_ANSWER_KEYWORD_MAP.items()
            if hindi in answer
        )
    answer_terms = terms(answer_context)
    question_terms = terms(f"{question} {query_context}")
    if not answer_terms:
        answer_terms |= question_terms

    text_by_id = {
        chunk.get("record_id"): chunk.get("text", "")
        for chunk in evidence_chunks
        if chunk.get("record_id")
    }
    supporting = []
    for source in sources:
        source_id = source.get("record_id")
        source_text = text_by_id.get(source_id, "")
        source_terms = terms(source_text)
        answer_overlap = len(answer_terms & source_terms)
        minimum_overlap = 2 if is_hindi_text(answer) else 3
        if answer_overlap >= minimum_overlap:
            supporting.append((source, answer_overlap))
    priorities = {
        "book": 0,
        "speech": 1,
        "interview": 2,
        "exhibit_context": 3,
        "article": 4,
        "biography": 4,
        "photo": 5,
    }
    supporting.sort(key=lambda item: (
        priorities.get(item[0].get("type", ""), 4),
        -item[1],
        item[0].get("distance", 1.0),
    ))
    return [source for source, _ in supporting[:4]]


def _best_fallback_chunk(
    question: str,
    search_queries: list[str],
    evidence_chunks: list[dict],
) -> dict | None:
    if not evidence_chunks:
        return None
    stop_words = {
        "about", "after", "also", "ambedkar", "and", "are", "been", "before",
        "being", "between", "both", "could", "did", "does", "from", "have",
        "here", "higher", "his", "into", "just", "more", "most", "new", "only",
        "other", "over", "that", "their", "them", "then", "there", "these",
        "they", "this", "those", "through", "under", "very", "what", "when",
        "where", "which", "while", "with", "would", "your", "the", "was", "were",
    }
    query_terms = {
        word for word in re.findall(r"[a-z0-9]+", f"{question} {' '.join(search_queries)}".lower())
        if len(word) > 2 and word not in stop_words
    }
    return max(
        evidence_chunks,
        key=lambda chunk: (
            len(query_terms & {
                word for word in re.findall(r"[a-z0-9]+", chunk.get("text", "").lower())
                if len(word) > 2 and word not in stop_words
            }),
            -(chunk.get("source") or {}).get("distance", 1.0),
        ),
    )


def _has_relevant_archive_context(
    question: str,
    search_queries: list[str],
    evidence_chunks: list[dict],
) -> bool:
    stop_words = {
        "about", "after", "also", "ambedkar", "and", "are", "been", "before",
        "being", "between", "both", "could", "did", "does", "from", "have",
        "here", "higher", "his", "into", "just", "more", "most", "new", "only",
        "other", "over", "that", "their", "them", "then", "there", "these",
        "they", "this", "those", "through", "under", "very", "what", "when",
        "where", "which", "while", "with", "would", "your", "the", "was", "were",
    }
    query_terms = {
        word for word in re.findall(r"[a-z0-9]+", f"{question} {' '.join(search_queries)}".lower())
        if len(word) > 2 and word not in stop_words
    }
    for chunk in evidence_chunks:
        chunk_terms = {
            word for word in re.findall(
                r"[a-z0-9]+",
                f"{chunk.get('topic', '')} {chunk.get('text', '')}".lower(),
            )
            if len(word) > 2 and word not in stop_words
        }
        if len(query_terms & chunk_terms) >= 2:
            return True
        distance = (chunk.get("source") or {}).get("distance")
        if distance is not None and distance <= 0.32:
            return True
    return False


def _filter_artifacts_to_sources(artifacts: list[dict], sources: list[dict]) -> list[dict]:
    source_ids = {source.get("record_id") for source in sources}
    return [artifact for artifact in artifacts if artifact.get("record_id") in source_ids]


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
async def chat_with_tools(transcript: str) -> tuple[str, list[dict], list[dict]]:
    """
    Search raw, normalized, and expanded queries before deciding whether evidence exists.
    """
    archive_search_queries = normalize_archive_queries(transcript)
    collected_artifacts: list[dict] = []
    collected_sources: list[dict] = []
    evidence_texts: list[str] = []
    evidence_chunks: list[dict] = []
    seen_source_ids: set[str] = set()
    seen_chunk_ids: set[str] = set()
    seen_artifacts: set[tuple[str, str]] = set()

    def collect_results(results: dict) -> None:
        for chunk in results.get("text_chunks", []):
            chunk_id = chunk.get("record_id") or ""
            if chunk.get("text") and chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk_id)
                evidence_texts.append(chunk["text"])
                evidence_chunks.append(chunk)
        for source in results.get("sources", []):
            record_id = source.get("record_id") or ""
            if record_id and record_id not in seen_source_ids:
                seen_source_ids.add(record_id)
                collected_sources.append(source)
        for artifact_type, key in (("photo", "images"), ("article", "articles")):
            for item in results.get(key, []):
                identity = (artifact_type, item.get("url", ""))
                if identity not in seen_artifacts:
                    seen_artifacts.add(identity)
                    collected_artifacts.append({"type": artifact_type, **item})

    for search_query in archive_search_queries:
        collect_results(search_artifacts(search_query))
    stop_words = {
        "about", "after", "also", "ambedkar", "and", "are", "been", "before",
        "being", "between", "both", "could", "did", "does", "from", "have",
        "here", "higher", "his", "into", "just", "more", "most", "new", "only",
        "other", "over", "that", "their", "them", "then", "there", "these",
        "they", "this", "those", "through", "under", "very", "what", "when",
        "where", "which", "while", "with", "would", "your", "the", "was", "were",
    }
    search_terms = {
        word for word in re.findall(r"[a-z0-9]+", f"{transcript} {' '.join(archive_search_queries)}".lower())
        if len(word) > 2 and word not in stop_words
    }
    evidence_chunks.sort(key=lambda chunk: (
        -len(search_terms & {
            word for word in re.findall(
                r"[a-z0-9]+",
                f"{chunk.get('topic', '')} {chunk.get('text', '')}".lower(),
            )
            if len(word) > 2 and word not in stop_words
        }),
        (chunk.get("source") or {}).get("distance", 1.0),
    ))
    evidence_texts[:] = [chunk["text"] for chunk in evidence_chunks]
    initial_results = {"text_chunks": evidence_chunks}
    log.info("Retrieved archive record IDs: %s", sorted(seen_source_ids))

    def finalize_answer(
        answer: str,
        preferred_source_ids: set[str] | None = None,
    ) -> tuple[str, list[dict], list[dict]]:
        if not _has_relevant_archive_context(transcript, archive_search_queries, evidence_chunks):
            if is_hindi_text(transcript):
                no_source_answer = "उपलब्ध अभिलेखागार में इस प्रश्न का उत्तर देने वाला प्रासंगिक स्रोत नहीं मिला।"
            else:
                no_source_answer = "I couldn't find a sufficiently relevant archive source for that question yet."
            return no_source_answer, [], []

        grounded_answer = _remove_unverified_quotes(answer, evidence_texts)
        supporting_sources = _select_supporting_sources(
            transcript,
            grounded_answer,
            collected_sources,
            evidence_chunks,
            " ".join(archive_search_queries),
        )
        if preferred_source_ids is not None:
            supporting_sources = [
                source for source in supporting_sources
                if source.get("record_id") in preferred_source_ids
            ]
        if not supporting_sources:
            fallback_chunk = next(
                (chunk for chunk in evidence_chunks if chunk.get("record_id") in (preferred_source_ids or set())),
                None,
            ) if preferred_source_ids is not None else _best_fallback_chunk(
                transcript, archive_search_queries, evidence_chunks
            )
            fallback_id = fallback_chunk.get("record_id") if fallback_chunk else None
            fallback_source = next(
                (source for source in collected_sources if source.get("record_id") == fallback_id),
                None,
            )
            if fallback_chunk and fallback_source:
                grounded_answer = fallback_chunk.get("text", "")[:700]
                supporting_sources = [fallback_source]
            else:
                if is_hindi_text(transcript):
                    no_source_answer = "उपलब्ध अभिलेखागार में इस प्रश्न का उत्तर देने वाला प्रासंगिक स्रोत नहीं मिला।"
                else:
                    no_source_answer = "I couldn't find a sufficiently relevant archive source for that question yet."
                return no_source_answer, [], []
        supporting_ids = {source.get("record_id") for source in supporting_sources}
        supporting_texts = [
            chunk["text"] for chunk in evidence_chunks
            if chunk.get("record_id") in supporting_ids
        ]
        grounded_answer = _remove_unverified_quotes(grounded_answer, supporting_texts)
        return (
            grounded_answer,
            _filter_artifacts_to_sources(collected_artifacts, supporting_sources),
            supporting_sources,
        )

    def grounded_fallback_answer() -> tuple[str, set[str]]:
        chunk = _best_fallback_chunk(transcript, archive_search_queries, evidence_chunks)
        if not chunk:
            return "", set()
        return chunk.get("text", "")[:700], {chunk.get("record_id", "")}

    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key.startswith("gsk_YOUR_KEY"):
        fallback_text, fallback_ids = grounded_fallback_answer()
        return finalize_answer(fallback_text, fallback_ids)

    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nSearch queries already tried: {archive_search_queries}\n\n{_format_archive_evidence(initial_results.get('text_chunks', []))}"},
        {"role": "user", "content": transcript},
    ]
    max_rounds = 5

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
                    search_query = fn_args.get("query")
                    if not isinstance(search_query, str) or not search_query.strip():
                        search_query = transcript
                    archive_search_queries.extend(normalize_archive_queries(search_query))
                    archive_search_queries = list(dict.fromkeys(archive_search_queries))[:ARCHIVE_MAX_SEARCH_QUERIES * 2]
                    result = search_artifacts(search_query)
                    collect_results(result)
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
            return finalize_answer(answer.strip())

        # If model returned no tool calls and empty content, nudge it once to reply
        messages.append({"role": "user", "content": "Please provide your concise voice tour guide response in the requested language."})

    # Fallback if rounds exhausted or empty
    fallback_text, fallback_ids = grounded_fallback_answer()
    return finalize_answer(fallback_text, fallback_ids)


# ── Exhibit-scoped chat (artifact context, no Chroma tools) ───────
async def chat_with_exhibit_context(
    qr_id: str,
    transcript: str,
    *,
    for_narration: bool = False,
    language: str = "en",
) -> str:
    """Send transcript to LLM with loaded exhibit markdown context."""
    system_prompt = build_exhibit_system_prompt(qr_id, for_narration=for_narration, language=language)
    key = os.getenv("GROQ_API_KEY", "").strip()

    if for_narration:
        if language == "hi":
            user_content = (
                "इस प्रदर्शनी का परिचय अभी हिंदी में दें। केवल ये सही तिथियां इस्तेमाल करें: "
                "संविधान 26 नवंबर 1949 को अपनाया गया, अंतिम हस्ताक्षर 24 जनवरी 1950 को पूरे हुए, "
                "और संविधान 26 जनवरी 1950 को लागू हुआ।"
            )
        else:
            user_content = "Please deliver the exhibit introduction now. Use only the verified exhibit dates in the context."
    else:
        user_content = transcript

    if not key or key.startswith("gsk_YOUR_KEY"):
        entry = get_artifact(qr_id)
        title = entry["title"] if entry else "this exhibit"
        if for_narration:
            narration = (
                f"Welcome to the {title} exhibit at the Dr. B.R. Ambedkar National Memorial. "
                "This display recreates the historic signing of the Constitution of India in January nineteen fifty, "
                "a moment central to Dr. Ambedkar's legacy as chief architect of the Constitution. "
                "The images beside you show pages from the original handwritten Constitution and "
                "Jawaharlal Nehru signing the document in the Constituent Assembly Hall."
            )
            if language == "hi":
                return "यह प्रदर्शनी डॉ. बी. आर. आंबेडकर राष्ट्रीय स्मारक में भारतीय संविधान पर हस्ताक्षर के ऐतिहासिक क्षण को दिखाती है। यहां आप संविधान पर हस्ताक्षर करते हुए सदस्यों का जीवन-आकार दृश्य, संविधान के हस्तलिखित पृष्ठ और जवाहरलाल नेहरू को हस्ताक्षर करते हुए देख सकते हैं। अंतिम हस्ताक्षर चौबीस जनवरी उन्नीस सौ पचास को पूरे हुए और संविधान छब्बीस जनवरी उन्नीस सौ पचास को लागू हुआ। डॉ. आंबेडकर प्रारूप समिति के अध्यक्ष और संविधान के प्रमुख वास्तुकार थे, इसलिए यह दृश्य उनके स्मारक में विशेष महत्व रखता है।"
            return narration
        if language == "hi":
            return "यह प्रदर्शनी भारतीय संविधान पर हस्ताक्षर के ऐतिहासिक क्षण और डॉ. आंबेडकर की प्रारूप समिति के अध्यक्ष तथा संविधान के प्रमुख वास्तुकार के रूप में भूमिका की कहानी बताती है।"
        if is_hindi_text(transcript):
            return "यह प्रदर्शनी भारतीय संविधान पर हस्ताक्षर के ऐतिहासिक क्षण को दर्शाती है, जिसमें डॉ. अंबेडकर की महत्वपूर्ण भूमिका शामिल है।"
        return f"This exhibit at the memorial tells the story of the Constitution signing and Dr. Ambedkar's role as its chief architect."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "temperature": 0.5,
        "max_tokens": 700 if not for_narration else 1400,
        "reasoning_effort": "low",
    }
    client = get_shared_client()
    try:
        resp = await client.post("/chat/completions", json=payload)
        if resp.status_code == 200:
            choice = resp.json()["choices"][0]
            answer = choice["message"].get("content", "") or ""
            if answer.strip():
                return answer.strip()
            log.error(
                "Exhibit chat returned no visible content: finish_reason=%s",
                choice.get("finish_reason"),
            )
        else:
            log.error(f"Exhibit chat error {resp.status_code}: {resp.text}")
    except Exception as e:
        log.error(f"Exhibit chat request failed: {e}")

    if for_narration:
        entry = get_artifact(qr_id)
        title = entry["title"] if entry else "this exhibit"
        if language == "hi":
            return "यह प्रदर्शनी भारतीय संविधान पर हस्ताक्षर के ऐतिहासिक क्षण को दिखाती है। यहां संविधान के हस्तलिखित पृष्ठ और हस्ताक्षर करते हुए जवाहरलाल नेहरू का चित्र दिखाई देता है। अंतिम हस्ताक्षर चौबीस जनवरी उन्नीस सौ पचास को पूरे हुए और संविधान छब्बीस जनवरी उन्नीस सौ पचास को लागू हुआ। डॉ. आंबेडकर प्रारूप समिति के अध्यक्ष और संविधान के प्रमुख वास्तुकार थे।"
        return f"This {title} exhibit shows the historic signing of India's Constitution. The display includes handwritten Constitution pages and a photograph of Jawaharlal Nehru signing the document. The final signatures were completed on January twenty-fourth, nineteen fifty, and the Constitution came into force on January twenty-sixth, nineteen fifty. Dr. Ambedkar chaired the Drafting Committee and is regarded as the Constitution's chief architect."
    if language == "hi":
        return "यह प्रदर्शनी भारतीय संविधान पर हस्ताक्षर और डॉ. आंबेडकर की प्रारूप समिति के अध्यक्ष के रूप में भूमिका के बारे में बताती है। कृपया अपना प्रश्न दोबारा पूछें, मैं इस प्रदर्शनी के तथ्यों के आधार पर उत्तर दूंगा।"
    if is_hindi_text(transcript):
        return "कृपया अपना प्रश्न दोबारा पूछें — मैं इस प्रदर्शनी के बारे में और बता सकता हूँ।"
    return "I can share more about this exhibit — please ask your question again."


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
    answer_text, artifacts, archive_sources = await chat_with_tools(transcript)
    log.info(f"Tour Guide Answer: {answer_text[:120]}…")

    # 4. Synthesise speech via Orpheus TTS
    audio_url = await synthesise_speech(answer_text)

    # 5. Return JSON payload
    return JSONResponse({
        "audio_url": audio_url,
        "text": answer_text,
        "transcript": transcript,
        "artifacts": artifacts,
        "archive_sources": archive_sources,
    })


# ── QR Artifact endpoints ──────────────────────────────────────────
@app.get("/artifact/{qr_id}")
async def get_artifact_info(qr_id: str):
    payload = artifact_payload(qr_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Unknown artifact: {qr_id}")
    return JSONResponse(payload)


@app.post("/artifact/{qr_id}/narrate")
async def narrate_artifact(qr_id: str, payload: Optional[dict] = Body(None)):
    if get_artifact(qr_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown artifact: {qr_id}")

    language = (payload or {}).get("language", "en")
    if language not in {"en", "hi"}:
        raise HTTPException(status_code=400, detail="Unsupported language. Use 'en' or 'hi'.")
    log.info(f"Narrating artifact: {qr_id} in {language}")
    narration = await chat_with_exhibit_context(qr_id, "", for_narration=True, language=language)
    audio_url = await synthesise_speech(narration)

    return JSONResponse({
        "audio_url": audio_url,
        "text": narration,
    })


@app.post("/artifact/{qr_id}/converse")
async def converse_artifact(
    qr_id: str,
    audio: Optional[UploadFile] = File(None),
    query: Optional[str] = Form(None),
    language: str = Form("en"),
):
    if get_artifact(qr_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown artifact: {qr_id}")
    if language not in {"en", "hi"}:
        raise HTTPException(status_code=400, detail="Unsupported language. Use 'en' or 'hi'.")

    if audio is not None:
        audio_bytes = await audio.read()
        if len(audio_bytes) >= 100:
            transcript = await transcribe(audio_bytes, audio.filename or "recording.webm")
        elif query:
            transcript = query
        else:
            transcript = "Tell me about this exhibit."
    elif query:
        transcript = query
    else:
        transcript = "Tell me about this exhibit."

    if not transcript.strip():
        return JSONResponse({
            "audio_url": None,
            "text": "I didn't catch that. Could you please tap and ask again?",
            "transcript": "",
        })

    log.info(f"Artifact converse [{qr_id}]: {transcript}")
    answer_text = await chat_with_exhibit_context(qr_id, transcript, language=language)
    audio_url = await synthesise_speech(answer_text)

    return JSONResponse({
        "audio_url": audio_url,
        "text": answer_text,
        "transcript": transcript,
    })


# ── Serve frontend pages ───────────────────────────────────────────
@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/exhibit")
async def serve_exhibit():
    return FileResponse(str(FRONTEND_DIR / "exhibit.html"))


# ── Health check ────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "chroma_docs": collection.count() if collection else 0,
        "groq_key_set": bool(GROQ_API_KEY),
    }


@app.get("/{spa_path:path}")
async def serve_kiosk_route(spa_path: str):
    """Serve the existing kiosk SPA for its client-side collection routes."""
    parts = [part for part in spa_path.split("/") if part]
    collections = {"exhibits", "books", "speeches", "interviews"}
    valid_route = (
        len(parts) == 1 and parts[0] in {*collections, "media", "assistant"}
    ) or (
        len(parts) == 2 and parts[0] in collections
    )
    if not valid_route:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# ── Cleanup ─────────────────────────────────────────────────────────
@app.on_event("shutdown")
async def shutdown():
    global _shared_client
    if _shared_client and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None
    # Clean up old audio files (>1 hour)
    cutoff = time.time() - 3600
    for f in list(AUDIO_DIR.glob("*.wav")) + list(AUDIO_DIR.glob("*.mp3")):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
