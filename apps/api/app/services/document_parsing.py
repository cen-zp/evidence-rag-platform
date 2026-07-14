from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


class DocumentParsingError(ValueError):
    """Raised when a stored document cannot be converted to text."""


@dataclass(frozen=True)
class ParsedPage:
    text: str
    page_number: int | None


def parse_document(path: Path, mime_type: str) -> list[ParsedPage]:
    if mime_type in {"text/markdown", "text/plain"}:
        return [_parse_markdown(path)]
    if mime_type == "application/pdf":
        return _parse_pdf(path)
    raise DocumentParsingError(f"Unsupported document type: {mime_type}")


def _parse_markdown(path: Path) -> ParsedPage:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise DocumentParsingError("Markdown files must be UTF-8 encoded") from error

    return ParsedPage(text=text, page_number=None)


def _parse_pdf(path: Path) -> list[ParsedPage]:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise DocumentParsingError("Encrypted PDF files are not supported")
        return [
            ParsedPage(text=page.extract_text() or "", page_number=index)
            for index, page in enumerate(reader.pages, start=1)
        ]
    except DocumentParsingError:
        raise
    except Exception as error:
        raise DocumentParsingError("PDF text extraction failed") from error
