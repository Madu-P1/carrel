# Carrel — Ingestion Coverage

> Source of truth: `services/extraction/utils.py:SUPPORTED_SUFFIXES` and `services/extraction/registry.py:parser_map`. Upload allowlist (`services/uploads.py:ALLOWED_SUFFIXES`) imports from the same set so the two cannot drift.

## Currently shippable (parser exists, upload allowed, end-to-end tested or trivially testable)

| Category | Suffix | Parser | Notes |
|---|---|---|---|
| Documents | `.pdf` | `parsers/pdf.py` | Primary. PDF.js native rendering. |
| Documents | `.docx` | `parsers/docx.py` | Word, modern. python-docx. |
| Documents | `.doc` | `parsers/legacy.py` | Word legacy. |
| Documents | `.rtf` | `parsers/rtf.py` | Rich text. |
| Documents | `.epub` | `parsers/epub.py` | Textbooks, e-books. **High student value.** |
| Documents | `.html`, `.htm` | `parsers/html.py` | Saved web articles, syllabi. |
| Documents | `.xml` | `parsers/html.py` | Reuses HTML parser path. |
| Slides | `.pptx` | `parsers/pptx.py` | Lecture slides. |
| Slides | `.ppt` | `parsers/legacy.py` | Legacy PowerPoint. |
| Spreadsheets | `.xlsx`, `.xls` | `parsers/xlsx.py` + legacy | Data/study tables. |
| Tabular | `.csv`, `.tsv` | `parsers/csv.py` | Datasets. |
| Structured | `.json`, `.jsonl` | `parsers/json.py` + text | Code outputs, transcripts. |
| Plain text | `.txt`, `.md`, `.markdown`, `.rst`, `.log`, `.tex` | `parsers/text.py` | Notes, summaries, READMEs. |
| Code | `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.c`, `.cpp`, `.h`, `.hpp`, `.rs`, `.go`, `.rb`, `.swift` | `parsers/text.py` | CS coursework. |
| Config | `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.conf` | `parsers/text.py` | Reading docs / spec files. |
| Subtitles | `.srt`, `.vtt` | `parsers/text.py` | Lecture transcripts. |
| Images | `.png`, `.jpg`, `.jpeg`, `.heic`, `.tiff`, `.tif`, `.bmp`, `.gif`, `.webp` | `parsers/image.py` | OCR for textbook photos, whiteboard captures. |
| Audio | `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg` | `parsers/media.py` | Lecture recordings. **High student value.** |
| Video | `.mp4`, `.mov`, `.m4v`, `.mkv`, `.avi`, `.webm` | `parsers/media.py` | Recorded lectures. Subject to 100MB upload cap. |

**Total formats live (post upload-allowlist fix, 2026-05-07):** 50+ extensions across 9 content categories.

## Conditional (parser exists, upload deliberately gated)

| Category | Suffix | Why gated |
|---|---|---|
| Archive | `.zip` | Per-entry size + format validation pass not yet implemented. Zip-bomb risk. Add bounded-extraction wrapper before allowing. |

## Known gaps the parser layer does not cover (ranked by student value)

1. **Web URLs (paste a link)** — students paste Wikipedia / Stack Overflow / lecture-page URLs constantly. Adding a URL ingestion endpoint that fetches HTML and routes through the existing `parse_html` parser is a half-day job and a major perceived expansion.
2. **Apple Notes export (`.notes` package or RTFD)** — students who already keep notes in Apple Notes hit a wall.
3. **Google Docs export** — currently requires manual export to DOCX. A Google-OAuth-based importer is a year-2 surface.
4. **`.pages`, `.numbers`, `.key`** — Apple iWork. Students on Apple ecosystems would expect this. Pages files are technically zip archives with embedded XML; doable.
5. **`.kcl`, `.cs`, `.kt`, `.scala`, `.dart`, `.lua`, `.r`** — additional code languages. Trivial to add (just append to `TEXT_SUFFIXES`).
6. **`.numbers` / `.xls` formula evaluation** — currently treats spreadsheets as text. Computing derived cells would matter for finance students.

## What changed in this commit

`services/uploads.py:ALLOWED_SUFFIXES` was a hand-maintained whitelist of 10 suffixes. It diverged from what the parser registry actually supports. Replaced with `SUPPORTED_SUFFIXES - {".zip"}` so:
- The upload UI now exposes the full extractor capability.
- Future parser additions automatically reach the upload path.
- Drift becomes structurally impossible.

## Validation

Before the next ship, manually upload one file of each new type:
- A textbook EPUB (Project Gutenberg has free EPUBs)
- A lecture MP3 (any podcast episode)
- A textbook page photo (PNG/JPG)
- A saved Wikipedia article (HTML "Save as" from Safari)
- A Markdown README
- A `.json` exam dataset

Confirm each ingests, chunks, and shows up in the Library with the correct subject grouping.
