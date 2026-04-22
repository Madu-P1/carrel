from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .chunking import ChunkBuilder
from .detector import FileTypeDetector
from .parsers.archive import parse_zip
from .parsers.common import ParserContext
from .parsers.csv import parse_csv
from .parsers.docx import parse_docx
from .parsers.epub import parse_epub
from .parsers.html import parse_html
from .parsers.image import parse_image
from .parsers.json import parse_json
from .parsers.legacy import parse_doc, parse_ppt, parse_xls
from .parsers.media import parse_audio, parse_video
from .parsers.pdf import parse_pdf
from .parsers.pptx import parse_pptx
from .parsers.rtf import parse_rtf
from .parsers.text import parse_text
from .parsers.xlsx import parse_xlsx
from .types import IngestedAsset
from .utils import SUPPORTED_SUFFIXES, TEXT_SUFFIXES


class ParserRegistry:
    def __init__(self) -> None:
        self.context = ParserContext(chunk_builder=ChunkBuilder())

    def extract(self, path: Path) -> IngestedAsset:
        suffix, mime_type = FileTypeDetector.detect(path)
        if suffix not in SUPPORTED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type {suffix or '(none)'}. Supported types: {', '.join(sorted(SUPPORTED_SUFFIXES))}",
            )

        parser_map = {
            ".pdf": parse_pdf,
            ".docx": parse_docx,
            ".doc": parse_doc,
            ".pptx": parse_pptx,
            ".ppt": parse_ppt,
            ".xlsx": parse_xlsx,
            ".xls": parse_xls,
            ".csv": parse_csv,
            ".tsv": parse_csv,
            ".html": parse_html,
            ".htm": parse_html,
            ".json": parse_json,
            ".jsonl": parse_text,
            ".xml": parse_html,
            ".epub": parse_epub,
            ".rtf": parse_rtf,
            ".zip": lambda target, *, suffix, mime_type, context: parse_zip(
                target,
                suffix=suffix,
                mime_type=mime_type,
                context=context,
                extractor=self.extract,
            ),
            ".png": parse_image,
            ".jpg": parse_image,
            ".jpeg": parse_image,
            ".heic": parse_image,
            ".tiff": parse_image,
            ".tif": parse_image,
            ".bmp": parse_image,
            ".gif": parse_image,
            ".webp": parse_image,
            ".mp3": parse_audio,
            ".wav": parse_audio,
            ".m4a": parse_audio,
            ".aac": parse_audio,
            ".flac": parse_audio,
            ".ogg": parse_audio,
            ".mp4": parse_video,
            ".mov": parse_video,
            ".m4v": parse_video,
            ".mkv": parse_video,
            ".avi": parse_video,
            ".webm": parse_video,
        }
        parser = parser_map.get(suffix)
        if parser is None and suffix in TEXT_SUFFIXES:
            parser = parse_text
        if parser is None:
            raise HTTPException(status_code=400, detail=f"No parser registered for {suffix}")
        return parser(path, suffix=suffix, mime_type=mime_type, context=self.context)


def extract_asset(path: Path) -> IngestedAsset:
    registry = ParserRegistry()
    asset = registry.extract(path)
    if not asset.cleaned_text.strip():
        raise HTTPException(
            status_code=400,
            detail=f"{path.name} was readable, but no grounded text could be extracted with enough confidence.",
        )
    return asset
