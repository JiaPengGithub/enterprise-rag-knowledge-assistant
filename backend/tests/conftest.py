import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_app(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT.parent)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("SAMPLE_DOCS_DIR", str(ROOT.parent / "data" / "sample_documents"))
    monkeypatch.setenv("OPENAI_API_KEY", "")

    from app.core.config import get_settings

    get_settings.cache_clear()

    from app.services.documents import seed_sample_documents
    from app.services.users import seed_users
    from app.storage.database import ensure_data_dirs, init_db

    ensure_data_dirs()
    init_db()
    seed_users()
    seed_sample_documents()
    yield
    get_settings.cache_clear()
