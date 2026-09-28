"""Ingest locally stored book/document text into the existing Chroma collection.

Run from the backend directory with its virtual environment active:
    python ingest_books.py

This does not modify the source files, recreate the collection, or perform OCR.
"""

from __future__ import annotations

import hashlib
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import chromadb
from pypdf import PdfReader

BACKEND_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = BACKEND_DIR.parent
BOOKS_DIR = REPOSITORY_DIR / "content" / "books"
SOURCES_FILE = REPOSITORY_DIR / "content" / "sources" / "SOURCES.md"
CHROMA_DIR = BACKEND_DIR / "chroma_db"
COLLECTION_NAME = "ambedkar_museum"
MAX_CHUNK_CHARS = 1000
MIN_PAGE_CHARS = 40
UPSERT_BATCH_SIZE = 256


def load_manifest_records() -> dict[str, dict[str, str]]:
    """Map content-relative paths to titles and URLs already in SOURCES.md."""
    records: dict[str, dict[str, str]] = {}
    if not SOURCES_FILE.is_file():
        return records

    for line in SOURCES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] == "Title" or cells[0].startswith("---"):
            continue
        local_paths = re.findall(r"`((?:books|speeches)/[^`]+)`", cells[2])
        source_urls = re.findall(r"\[[^\]]+\]\((https?://[^)]+)\)", cells[3])
        if not local_paths:
            continue
        for local_path in local_paths:
            records[Path("content").joinpath(local_path).as_posix()] = {
                "document_title": cells[0],
                "source_url": source_urls[0] if source_urls else "",
            }
    return records


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = (text.replace("\x00", "").replace("\ufeff", "")
            .replace("\u00ad", "").replace("\ufffd", "").replace("\u200b", ""))
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph).strip()


def split_long_text(text: str, limit: int) -> list[str]:
    """Split long sentence fragments at word boundaries where possible."""
    words = text.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        if len(word) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(word[index:index + limit] for index in range(0, len(word), limit))
        elif current and len(current) + len(word) + 1 > limit:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_page_text(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Pack sentence-aligned text from a single page into bounded chunks."""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            fragments = [sentence] if len(sentence) <= limit else split_long_text(sentence, limit)
            for fragment in fragments:
                candidate = f"{current}\n\n{fragment}".strip() if current else fragment
                if current and len(candidate) > limit:
                    chunks.append(current)
                    current = fragment
                else:
                    current = candidate
    if current:
        chunks.append(current)
    return chunks


def document_id_for(source_path: str) -> str:
    digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()[:20]
    return f"book-{digest}"


def verified_contributors(text: str, pdf_author: str = "") -> dict[str, str]:
    """Return contributors only when the file itself explicitly identifies them."""
    sample = text[:20000]
    metadata: dict[str, str] = {}
    if "ambedkar" in pdf_author.lower():
        metadata["author"] = "Dr. B. R. Ambedkar"
    elif re.search(r"AUTHOR OF THE BOOK\s*:\s*Dr\.?\s*Bhimrao Ramji Ambedkar", sample, re.I):
        metadata["author"] = "Dr. Bhimrao Ramji Ambedkar"
    elif re.search(r"Babasaheb\s+Dr\.?\s*B\.?\s*R\.?\s*Ambedkar", sample, re.I):
        metadata["author"] = "Dr. B. R. Ambedkar"

    if re.search(r"SPEECHES DELIVERED BY\s+Dr\.?\s*Babasaheb Ambedkar", sample, re.I):
        metadata["speaker"] = "Dr. Babasaheb Ambedkar"
    compiler = re.search(r"COMPILED BY\s+Dr\.?\s+Anant Kalse", sample, re.I)
    if compiler:
        metadata["compiler"] = "Dr. Anant Kalse"
    if re.search(r"DECEMBER,?\s*2015", sample, re.I):
        metadata["year"] = 2015
    return metadata


def make_chunks(
    pages: list[tuple[int | None, str]],
    source_path: str,
    source_file: str,
    manifest: dict[str, str],
    document_type: str,
    contributors: dict[str, str],
) -> list[dict[str, Any]]:
    stable_document_id = document_id_for(source_path)
    title = manifest.get("document_title") or Path(source_file).stem.replace("_", " ")
    topic_type = "speech" if document_type == "speech_collection" else "book"
    chunks: list[dict[str, Any]] = []
    chunk_index = 0

    for page_number, raw_text in pages:
        text = clean_text(raw_text)
        if len(text) < MIN_PAGE_CHARS:
            continue
        for page_chunk_index, chunk_text in enumerate(chunk_page_text(text), start=1):
            if len(chunk_text.strip()) < MIN_PAGE_CHARS:
                continue
            chunk_index += 1
            page_part = f"p{page_number:05d}" if page_number is not None else "p00000"
            chunk_id = f"{stable_document_id}-{page_part}-c{page_chunk_index:04d}"
            metadata: dict[str, Any] = {
                "document_id": stable_document_id,
                "document_title": title,
                "source_file": source_file,
                "document_type": document_type,
                "source_path": source_path,
                "chunk_index": chunk_index,
                "type": topic_type,
                "topic": title,
            }
            if page_number is not None:
                metadata["page_number"] = page_number
            if manifest.get("source_url"):
                metadata["source_url"] = manifest["source_url"]
            metadata.update(contributors)
            chunks.append({"id": chunk_id, "text": chunk_text, "metadata": metadata})
    return chunks


def extract_pdf(path: Path, relative_path: str, manifest: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    reader = PdfReader(str(path), strict=False)
    pages: list[tuple[int | None, str]] = []
    page_errors: list[str] = []
    contributor_text: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
            if page_number <= 12:
                contributor_text.append(text)
            pages.append((page_number, text))
        except Exception as exc:
            page_errors.append(f"page {page_number}: {exc}")
            pages.append((page_number, ""))
    first_pages = "\n".join(contributor_text)
    pdf_author = str(reader.metadata.author or "") if reader.metadata else ""
    document_type = "speech_collection" if "cpa speeches" in manifest.get("document_title", "").lower() else "book"
    chunks = make_chunks(
        pages,
        relative_path,
        path.name,
        manifest,
        document_type,
        verified_contributors(first_pages, pdf_author),
    )
    return chunks, page_errors


def extract_text_file(path: Path, relative_path: str, manifest: dict[str, str]) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if "\ufffd" in text:
        text = text.replace("\ufffd", "")
    if "\f" in text:
        pages = [(number, page) for number, page in enumerate(text.split("\f"), start=1)]
    else:
        pages = [(None, text)]
    document_type = "speech_collection" if "cpa speeches" in manifest.get("document_title", "").lower() else "book"
    return make_chunks(
        pages,
        relative_path,
        path.name,
        manifest,
        document_type,
        verified_contributors(text[:20000]),
    )


def load_existing_ids(collection: Any, chunk_ids: list[str]) -> set[str]:
    existing: set[str] = set()
    for offset in range(0, len(chunk_ids), UPSERT_BATCH_SIZE):
        batch = chunk_ids[offset:offset + UPSERT_BATCH_SIZE]
        result = collection.get(ids=batch, include=["metadatas"])
        existing.update(result["ids"])
    return existing


def upsert_chunks(collection: Any, chunks: list[dict[str, Any]], existing_ids: set[str]) -> tuple[int, list[str]]:
    new_count = 0
    failures: list[str] = []
    new_chunks = [chunk for chunk in chunks if chunk["id"] not in existing_ids]
    for offset in range(0, len(new_chunks), UPSERT_BATCH_SIZE):
        batch = new_chunks[offset:offset + UPSERT_BATCH_SIZE]
        try:
            collection.upsert(
                ids=[chunk["id"] for chunk in batch],
                documents=[chunk["text"] for chunk in batch],
                metadatas=[chunk["metadata"] for chunk in batch],
            )
            new_count += len(batch)
            existing_ids.update(chunk["id"] for chunk in batch)
        except Exception as exc:
            failures.append(f"chunk batch {offset + 1}-{offset + len(batch)}: {exc}")
    return new_count, failures


def ingest() -> int:
    if not BOOKS_DIR.is_dir():
        print(f"Books directory not found: {BOOKS_DIR}")
        return 1
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        collection = client.get_collection("ambedkar_museum")
    except Exception as exc:
        print(f"Existing Chroma collection is unavailable; no collection was created: {exc}")
        return 1

    before_count = collection.count()
    manifest_records = load_manifest_records()
    pdf_paths = sorted(BOOKS_DIR.rglob("*.pdf"))
    txt_paths = sorted(BOOKS_DIR.rglob("*.txt"))
    txt_by_pdf = {path.with_suffix(".pdf"): path for path in txt_paths}
    consumed_txt: set[Path] = set()
    failures: list[str] = []
    fallbacks: list[str] = []
    skipped_companions: list[str] = []
    successful_documents = 0
    added_chunks = 0

    for pdf_path in pdf_paths:
        relative_pdf = pdf_path.relative_to(REPOSITORY_DIR).as_posix()
        manifest = manifest_records.get(relative_pdf, {})
        try:
            chunks, page_errors = extract_pdf(pdf_path, relative_pdf, manifest)
        except Exception as exc:
            chunks, page_errors = [], [str(exc)]

        if chunks:
            successful_documents += 1
            ids = [chunk["id"] for chunk in chunks]
            existing_ids = load_existing_ids(collection, ids)
            added, insert_errors = upsert_chunks(collection, chunks, existing_ids)
            added_chunks += added
            failures.extend(f"{relative_pdf} {error}" for error in insert_errors)
            failures.extend(f"{relative_pdf} {error}" for error in page_errors)
            companion = txt_by_pdf.get(pdf_path)
            if companion:
                consumed_txt.add(companion)
                skipped_companions.append(companion.relative_to(REPOSITORY_DIR).as_posix())
            print(f"INGESTED {relative_pdf}: {len(chunks)} chunks ({added} new)")
            continue

        failures.append(f"{relative_pdf}: no usable PDF text extracted; OCR was not attempted")
        companion = txt_by_pdf.get(pdf_path)
        if companion:
            relative_txt = companion.relative_to(REPOSITORY_DIR).as_posix()
            try:
                fallback_chunks = extract_text_file(companion, relative_txt, manifest_records.get(relative_txt, manifest))
                if fallback_chunks:
                    successful_documents += 1
                    existing_ids = load_existing_ids(collection, [chunk["id"] for chunk in fallback_chunks])
                    added, insert_errors = upsert_chunks(collection, fallback_chunks, existing_ids)
                    added_chunks += added
                    failures.extend(f"{relative_txt} {error}" for error in insert_errors)
                    fallbacks.append(f"{relative_pdf} -> {relative_txt}")
                    consumed_txt.add(companion)
                    print(f"FALLBACK {relative_txt}: {len(fallback_chunks)} chunks ({added} new)")
                else:
                    failures.append(f"{relative_txt}: no usable text")
            except Exception as exc:
                failures.append(f"{relative_txt}: {exc}")
                consumed_txt.add(companion)

    for text_path in txt_paths:
        if text_path in consumed_txt:
            continue
        relative_path = text_path.relative_to(REPOSITORY_DIR).as_posix()
        try:
            chunks = extract_text_file(text_path, relative_path, manifest_records.get(relative_path, {}))
            if not chunks:
                failures.append(f"{relative_path}: no usable text")
                continue
            successful_documents += 1
            existing_ids = load_existing_ids(collection, [chunk["id"] for chunk in chunks])
            added, insert_errors = upsert_chunks(collection, chunks, existing_ids)
            added_chunks += added
            failures.extend(f"{relative_path} {error}" for error in insert_errors)
            print(f"INGESTED {relative_path}: {len(chunks)} chunks ({added} new)")
        except Exception as exc:
            failures.append(f"{relative_path}: {exc}")

    after_count = collection.count()
    print("\nIngestion summary")
    print(f"Source files discovered: {len(pdf_paths) + len(txt_paths)}")
    print(f"Documents ingested: {successful_documents}")
    print(f"TXT companions skipped: {len(skipped_companions)}")
    for relative_path in skipped_companions:
        print(f"  SKIPPED DUPLICATE COMPANION {relative_path}")
    print(f"TXT fallbacks used: {len(fallbacks)}")
    for fallback in fallbacks:
        print(f"  FALLBACK {fallback}")
    print(f"Chunks added: {added_chunks}")
    print(f"Chroma count: {before_count} -> {after_count}")
    print(f"Failures: {len(failures)}")
    for failure in failures:
        print(f"  FAILED {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(ingest())
