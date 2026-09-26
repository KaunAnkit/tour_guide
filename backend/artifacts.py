"""
Artifact registry and context loading for QR-scanned exhibits.
Add new entries to ARTIFACT_REGISTRY to support additional QR artifacts.
"""

from __future__ import annotations

import pathlib
import json
import re
from typing import Any, Optional

BASE_DIR = pathlib.Path(__file__).parent
QR_DATA_DIR = BASE_DIR.parent / "qr_data"

ARTIFACT_REGISTRY: dict[str, dict[str, Any]] = {
    "constitution_signing": {
        "id": "DANM-EXH-001",
        "aliases": ["DANM-EXH-001", "danm-exh-001"],
        "title": "Constitution Signing",
        "display_title": "CONSTITUTION SIGNING",
        "folder": "constitution_signing",
        "context_file": "artifact-context-01-constitution-signing.md",
        "images": [
            {
                "filename": "constitution.png",
                "context_file": "constitution-image-context.md",
                "alt": "Pages from the handwritten Constitution of India",
                "title": "Handwritten Constitution",
                "caption": "Calligraphed pages of the Constitution of India, adopted 26 November 1949.",
            },
            {
                "filename": "nehrusigning.png",
                "context_file": "nehrusigning-image-context.md",
                "alt": "Jawaharlal Nehru signing the Constitution of India",
                "title": "Nehru Signing",
                "caption": "Jawaharlal Nehru signs the Constitution in the Constituent Assembly Hall, January 1950.",
            },
        ],
    },
}


def get_artifact(qr_id: str) -> Optional[dict[str, Any]]:
    """Return registry entry for a QR id, museum ID, or alias."""
    if not qr_id:
        return None
    key = qr_id.strip()
    if key in ARTIFACT_REGISTRY:
        return ARTIFACT_REGISTRY[key]

    key_lower = key.lower()
    for entry in ARTIFACT_REGISTRY.values():
        if entry.get("id", "").lower() == key_lower:
            return entry
        aliases = entry.get("aliases") or []
        if any(a.lower() == key_lower for a in aliases):
            return entry
    return None


def _artifact_dir(entry: dict[str, Any]) -> pathlib.Path:
    return QR_DATA_DIR / entry["folder"]


def _read_md(path: pathlib.Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return ""


def load_artifact_context(qr_id: str) -> str:
    """Load all markdown context for an artifact (main + per-image)."""
    entry = get_artifact(qr_id)
    if not entry:
        return ""

    base = _artifact_dir(entry)
    parts: list[str] = []

    main_ctx = _read_md(base / entry["context_file"])
    if main_ctx:
        parts.append(main_ctx)

    images_dir = base / "images"
    for img in entry.get("images", []):
        ctx = _read_md(images_dir / img["context_file"])
        if ctx:
            parts.append(ctx)

    return "\n\n---\n\n".join(parts)


RELATED_CONTENT_KEYS = ("related_speeches", "related_locations", "related_books")
RELATED_CONTENT_HEADING = re.compile(
    r"(?ims)^###\s+Related content for UI[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)"
)


def _artifact_markdown(entry: dict[str, Any]) -> str:
    return _read_md(_artifact_dir(entry) / entry["context_file"])


def artifact_id(qr_id: str) -> Optional[str]:
    entry = get_artifact(qr_id)
    if not entry:
        return None
    match = re.search(r"(?m)^##\s+artifact_id:\s*(\S+)\s*$", _artifact_markdown(entry))
    return match.group(1) if match else entry["id"]


def related_content(qr_id: str) -> dict[str, list[dict[str, Any]]]:
    """Read optional UI cards from the exhibit's fenced JSON section."""
    empty = {key: [] for key in RELATED_CONTENT_KEYS}
    entry = get_artifact(qr_id)
    if not entry:
        return empty

    match = RELATED_CONTENT_HEADING.search(_artifact_markdown(entry))
    if not match:
        return empty

    code = re.search(r"(?is)```(?:json)?\s*(.*?)\s*```", match.group(1))
    if not code:
        return empty
    try:
        data = json.loads(code.group(1))
    except json.JSONDecodeError:
        return empty
    if not isinstance(data, dict):
        return empty

    stable_id = artifact_id(qr_id)
    result = {}
    for key in RELATED_CONTENT_KEYS:
        entries = data.get(key)
        result[key] = [
            {**item, "artifact_id": stable_id}
            for item in entries
            if isinstance(item, dict)
        ] if isinstance(entries, list) else []
    return result


def related_content_for_artifacts(artifact_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Combine source-backed UI content for the unique retrieved artifact IDs."""
    combined = {key: [] for key in RELATED_CONTENT_KEYS}
    seen: set[tuple[str, str]] = set()
    for identifier in artifact_ids:
        entry = get_artifact(identifier)
        if not entry:
            continue
        for key, items in related_content(entry["id"]).items():
            for item in items:
                identity = (key, json.dumps(item, sort_keys=True, ensure_ascii=False))
                if identity not in seen:
                    seen.add(identity)
                    combined[key].append(item)
    return combined


def artifact_chroma_documents(max_length: int = 900) -> list[dict[str, Any]]:
    """Build stable Chroma documents from exhibit Markdown and related UI data."""
    documents: list[dict[str, Any]] = []
    for entry in ARTIFACT_REGISTRY.values():
        identifier = artifact_id(entry["id"]) or entry["id"]
        context = load_artifact_context(entry["id"])
        context = RELATED_CONTENT_HEADING.sub("", context)
        paragraphs = re.split(r"\n\s*\n", context)
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if current and len(current) + len(paragraph) + 2 > max_length:
                chunks.append(current)
                current = ""
            while len(paragraph) > max_length:
                chunks.append(paragraph[:max_length])
                paragraph = paragraph[max_length:]
            current = f"{current}\n\n{paragraph}".strip()
        if current:
            chunks.append(current)

        for index, text in enumerate(chunks, start=1):
            documents.append({
                "id": f"md-{identifier}-{index:03d}",
                "text": text,
                "metadata": {
                    "type": "exhibit_context",
                    "topic": entry["title"],
                    "artifact_id": identifier,
                },
            })

        content_types = {
            "related_speeches": "speech",
            "related_locations": "location",
            "related_books": "book",
        }
        fields_by_type = {
            "speech": ("speaker", "date", "venue", "summary"),
            "location": ("city", "description"),
            "book": ("author", "year", "publisher", "description"),
        }
        for key, items in related_content(entry["id"]).items():
            content_type = content_types[key]
            for index, item in enumerate(items, start=1):
                fields = fields_by_type[content_type]
                parts = [f"Related {content_type}: {item.get('title') or item.get('name', '')}."]
                parts.extend(
                    f"{field.replace('_', ' ').title()}: {item[field]}."
                    for field in fields
                    if item.get(field) is not None and item.get(field) != ""
                )
                documents.append({
                    "id": f"md-{identifier}-{content_type}-{index:03d}",
                    "text": " ".join(parts),
                    "metadata": {
                        "type": f"related_{content_type}",
                        "topic": item.get("title") or item.get("name", ""),
                        "artifact_id": identifier,
                    },
                })
    return documents


def image_url(qr_id: str, filename: str) -> str:
    entry = get_artifact(qr_id)
    if not entry:
        return ""
    folder = entry["folder"]
    return f"/qr_data/{folder}/images/{filename}"


def artifact_payload(qr_id: str) -> Optional[dict[str, Any]]:
    """Build JSON-serialisable artifact info for GET /artifact/{qr_id}."""
    entry = get_artifact(qr_id)
    if not entry:
        return None

    images = [
        {
            "url": image_url(qr_id, img["filename"]),
            "alt": img.get("alt", ""),
            "filename": img["filename"],
            "title": img.get("title") or img.get("alt", ""),
            "caption": img.get("caption") or img.get("alt", ""),
            "type": "photo",
        }
        for img in entry.get("images", [])
    ]

    return {
        "id": artifact_id(qr_id) or entry["id"],
        "artifact_id": artifact_id(qr_id) or entry["id"],
        "qr_id": entry["folder"],
        "title": entry["title"],
        "display_title": entry.get("display_title", entry["title"].upper()),
        "images": images,
        **related_content(qr_id),
    }


ARTIFACT_SYSTEM_BASE = """You are an expert voice tour guide at the Dr. B.R. Ambedkar National Memorial.
You are standing beside a specific exhibit that the visitor scanned with a QR code.
Answer only using the exhibit context provided below and well-established historical facts.
Do not invent names of people in photographs or statues unless confirmed in the context.
Do not invent related speeches, locations, books, dates, source URLs, or audio; related UI cards are rendered from structured exhibit data.
If asked about unidentified figures, say they are members of the Constituent Assembly or refer to on-site signage.

Multilingual Output Rules:
• Respond in the exact same language the visitor uses.
• If the visitor asks in Hindi (Devanagari or Romanized), respond in natural conversational Hindi using Devanagari script.
• If the visitor asks in English, respond in English.

Voice Guide Guidelines:
• Keep answers concise: 2 to 3 engaging spoken sentences (under 50 words) unless narrating.
• Never use markdown, bullet points, or lists — plain spoken sentences only.
• In English: write years as spoken words (e.g. "nineteen forty-nine" not "1949").
• In Hindi: write years naturally in Devanagari words or numerals.
"""

ARTIFACT_NARRATION_PROMPT = """You are an expert voice tour guide at the Dr. B.R. Ambedkar National Memorial.
The visitor just scanned this exhibit's QR code. Deliver a welcoming spoken introduction.

Requirements:
• Write exactly 3 to 5 complete sentences.
• Introduce what the visitor sees and why it matters to Dr. Ambedkar's legacy.
• Mention the displayed images naturally if relevant.
• Use only facts from the exhibit context below.
• Mandatory facts for this exhibit: the Constitution was adopted on 26 November 1949, the final handwritten copies were signed on 24 January 1950, and it came into force on 26 January 1950.
• Never replace those dates with another year. Do not say January 2000, 2001, or any date other than the dates stated above.
• Do not claim that individual statues are identifiable unless the exhibit signage confirms their names.
• Plain spoken English unless the exhibit context specifies otherwise.
• No markdown, bullet points, or lists.
• In English: write years as spoken words (e.g. "nineteen fifty" not "1950").
"""


def build_exhibit_system_prompt(
    qr_id: str,
    *,
    for_narration: bool = False,
    language: str = "en",
) -> str:
    """Combine base prompt, optional narration instructions, and loaded context."""
    context = load_artifact_context(qr_id)
    base = ARTIFACT_NARRATION_PROMPT if for_narration else ARTIFACT_SYSTEM_BASE
    language_name = "Hindi (Devanagari script)" if language == "hi" else "English"
    language_instruction = f"\n\nOutput language requirement: Respond only in {language_name}."
    if context:
        return f"{base}{language_instruction}\n\n--- EXHIBIT CONTEXT ---\n\n{context}"
    return f"{base}{language_instruction}"
