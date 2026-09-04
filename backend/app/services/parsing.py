from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedPage:
    page: int | None
    text: str


def parse_document(path: Path) -> list[ParsedPage]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix == ".docx":
        return _parse_docx(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return [ParsedPage(page=1, text=path.read_text(encoding="utf-8", errors="ignore"))]
    raise ValueError("Unsupported file type. Upload PDF, DOCX, TXT, or Markdown files.")


def _parse_pdf(path: Path) -> list[ParsedPage]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF parsing requires the pypdf package.") from exc
    reader = PdfReader(str(path))
    pages: list[ParsedPage] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append(ParsedPage(page=index, text=page.extract_text() or ""))
    return pages


def _parse_docx(path: Path) -> list[ParsedPage]:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("DOCX parsing requires the python-docx package.") from exc
    document = Document(str(path))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return [ParsedPage(page=1, text=text)]
