from dataclasses import dataclass
from hashlib import sha1

from app.core.config import get_settings
from app.services.parsing import ParsedPage


@dataclass
class TextChunk:
    id: str
    page: int | None
    content: str
    token_count: int


def chunk_pages(document_id: str, version: int, pages: list[ParsedPage]) -> list[TextChunk]:
    settings = get_settings()
    chunks: list[TextChunk] = []
    for page in pages:
        for content in _split_text(page.text, settings.chunk_size, settings.chunk_overlap):
            digest = sha1(f"{document_id}:{version}:{page.page}:{content}".encode("utf-8")).hexdigest()[:16]
            chunks.append(
                TextChunk(
                    id=f"{document_id}-v{version}-{digest}",
                    page=page.page,
                    content=content,
                    token_count=len(content.split()),
                )
            )
    return chunks


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        return []
    words = text.split()
    if len(words) <= size:
        return [" ".join(words)]
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(end - overlap, start + 1)
    return chunks
