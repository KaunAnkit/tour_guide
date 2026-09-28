"""
Artifact registry and context loading for QR-scanned exhibits.
Add new entries to ARTIFACT_REGISTRY to support additional QR artifacts.
"""

from __future__ import annotations

import pathlib
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
        "id": entry["id"],
        "qr_id": entry["folder"],
        "title": entry["title"],
        "display_title": entry.get("display_title", entry["title"].upper()),
        "images": images,
    }


ARTIFACT_SYSTEM_BASE = """You are an expert voice tour guide at the Dr. B.R. Ambedkar National Memorial.
You are standing beside a specific exhibit that the visitor scanned with a QR code.
Answer only using the exhibit context provided below and well-established historical facts.
Do not invent names of people in photographs or statues unless confirmed in the context.
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
