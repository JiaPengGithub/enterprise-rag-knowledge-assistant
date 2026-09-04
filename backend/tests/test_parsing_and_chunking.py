from app.services.chunking import chunk_pages
from app.services.parsing import ParsedPage, parse_document


def test_markdown_parsing_preserves_page_metadata(tmp_path):
    path = tmp_path / "policy.md"
    path.write_text("# Policy\n\nEmployees submit requests ten days early.", encoding="utf-8")

    pages = parse_document(path)
    chunks = chunk_pages("doc1", 1, pages)

    assert pages[0].page == 1
    assert chunks
    assert chunks[0].page == 1
    assert "ten days" in chunks[0].content


def test_chunking_splits_long_pages(monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "chunk_size", 10)
    monkeypatch.setattr(settings, "chunk_overlap", 2)

    text = " ".join(f"word{i}" for i in range(25))
    chunks = chunk_pages("doc2", 1, [ParsedPage(page=3, text=text)])

    assert len(chunks) == 3
    assert all(chunk.page == 3 for chunk in chunks)
