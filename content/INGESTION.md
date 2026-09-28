# BODH Archival Ingestion Preparation

This document describes the current repository behavior and a compatible future path. It is preparation only: archival files have not been extracted, transcribed, chunked, or added to Chroma by this document.

## Current RAG Implementation

- `backend/seed_chroma.py` defines a static Python list of 20 biography, speech, photo, and article records. Each has a Chroma record ID and text; metadata currently uses `type` and `topic`, with `image_url` for photos and `url` for articles.
- The seeder creates or opens the persistent `ambedkar_museum` collection at `backend/chroma_db`, configures cosine distance, and calls `collection.upsert(ids, documents, metadatas)`. It does not read `content/books/` or `content/speeches/`, extract PDFs, or build archival transcript chunks. No explicit embedding model is configured in these source files; text is supplied to Chroma.
- `backend/main.py` opens that persistent collection at startup. `search_artifacts()` optionally expands known Hindi terms, queries Chroma with `n_results=3`, and maps retrieved `type`/`topic` metadata plus photo/article URLs into results. `/converse` still transcribes the visitor's submitted audio, calls the LLM/tool retrieval path, synthesizes speech, and returns `audio_url`, `text`, `transcript`, and `artifacts`.
- `main.py` also sends visitor-uploaded audio to Groq Whisper, but only returns its plain `text`. This is not an archival batch transcription pipeline and does not retain timestamps. The `_chunk_text()` helper is used for TTS output, not for source-document ingestion.
- `backend/artifacts.py` separately loads QR exhibit Markdown to build exhibit-specific prompts; it is not a general book or speech-media importer.

The current local Chroma database reports 51 records and contains metadata keys beyond those emitted by the checked-in static seeder (including `artifact_id` and related-content types). The source seeder defines 20 records and does not remove old records before upserting, so persistent database contents can outlive or differ from its current source list. Do not treat the local database alone as a reproducible source manifest.

## Future Book/Text Path

```text
content/books/ PDF or TXT
  -> extract text (PDF page by page; plain text directly)
  -> preserve page number/source location where available
  -> chunk with stable source and chunk identifiers
  -> upsert document text and scalar metadata into the existing Chroma collection
  -> retrieve through the existing search_artifacts path
```

No PDF/text file extraction from `content/books/` is implemented yet. Keep the existing static seed records working; a future importer should be a separate, explicit ingestion step and should not silently run during `/converse`.

## Future Audio/Video Path

```text
content/speeches/audio/ or content/speeches/video/
  -> speech-to-text (not implemented for stored archival media)
  -> timestamped transcript segments with verified source file references
  -> chunk while retaining each segment's start/end time
  -> upsert transcript chunks and scalar metadata into the existing Chroma collection
  -> retrieve through the existing search_artifacts path
```

The current Whisper request handler is only for visitor audio sent to `/converse`; there is no archival audio/video scanning, video decoding, timestamped transcription, or transcript indexing. Do not represent media as searchable transcript content until those stages actually run.

## Suggested Chunk Metadata

Use the Chroma record ID as a stable `document_id` (or include the same value as scalar metadata if consumers need it). For future chunks, preserve fields when known:

| Field | Meaning |
|---|---|
| `document_id` | Stable document/chunk identifier; never derive from chunk text alone. |
| `title` | Source document or speech title. |
| `author` / `speaker` | Verified author or speaker; use the applicable field. |
| `document_type` | For example `book`, `text`, `speech_transcript`, or `video_transcript`. |
| `source` | Source URL or other provenance reference. |
| `year` / `date` | Only when verified; do not infer missing dates. |
| `page_number` | PDF page where the extracted text came from, when available. |
| `timestamp_start` / `timestamp_end` | Transcript segment bounds in seconds, when available. |
| `file_path` | Repository-relative path to the original local source. |
| `language` | Verified or detected language, if available. |

Omit unknown fields rather than inventing values. Keep original media and archival documents unchanged. Store the original URL and attribution/licensing details in the source manifest. The transcript/chunk importer should add records to the current collection without changing `/converse` request or response contracts.

## Current Content Inventory

Books and source files are under `content/books/` and `content/sources/SOURCES.md`. Speech media folders are `content/speeches/audio/` and `content/speeches/video/`. The repository currently has a BBC interview MP4 in the video folder; no audio file or timestamped transcript has been produced here.
