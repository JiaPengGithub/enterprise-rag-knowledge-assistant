import sqlite3
from io import BytesIO

from fastapi.testclient import TestClient

from app.main import create_app


def test_init_db_adds_classification_to_existing_documents_table(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            department TEXT NOT NULL,
            roles TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    from app.core.config import get_settings
    from app.storage.database import init_db

    get_settings.cache_clear()
    init_db()

    connection = sqlite3.connect(database_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()}
    connection.close()
    get_settings.cache_clear()

    assert "classification" in columns


def test_chat_api_returns_citations(isolated_app):
    client = TestClient(create_app())

    response = client.post(
        "/api/chat",
        json={"question": "How many days in advance should employees request planned vacation?", "user_id": "hr_user"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["citations"]
    assert body["citations"][0]["document_title"] == "Employee Handbook"


def test_upload_document_api(isolated_app):
    client = TestClient(create_app())
    file = BytesIO(b"Security badges must be returned on the final day of employment.")

    response = client.post(
        "/api/documents/upload",
        data={"title": "Badge Policy", "department": "Security", "roles": "employee", "classification": "public"},
        files={"file": ("badge_policy.txt", file, "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Badge Policy"
    assert body["classification"] == "public"
    assert body["version"] == 1


def test_update_document_classification_api(isolated_app):
    client = TestClient(create_app())
    documents = client.get("/api/documents").json()
    document_id = documents[0]["id"]

    response = client.patch(f"/api/documents/{document_id}", json={"classification": "public"})

    assert response.status_code == 200
    body = response.json()
    assert body["classification"] == "public"


def test_evaluation_api_returns_metrics(isolated_app):
    client = TestClient(create_app())

    response = client.post("/api/evaluations/run")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert "hit_rate" in body
